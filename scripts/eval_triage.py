"""Labeled triage eval: category, Gatekeeper and memory across scenario labels.

Scenarios are fixture-derived; the expected labels are written by hand in this
file (synthetic scenario labels, not human-reviewed production data).

Usage: python scripts/eval_triage.py [--json]
Exits non-zero when any case fails.
"""

import argparse
import json
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db import Database
from backend.llm.stub import StubLLM
from backend.triage import EnrichmentPipeline
from backend.webhook import parse_ring_payload

TS = "2026-09-15T09:45:00Z"
TS_MS = 1789465500000
DEVICE = "ring_doorbell_01"

BASE = json.loads((ROOT / "mock" / "events" / "doorbell_unknown.json").read_text(encoding="utf-8"))

FIXTURES = {
    "doorbell_med": ("MED_DELIVERY", "grounded", "unverified", "high"),
    "doorbell_package_window": ("PACKAGE_DELIVERY", "grounded", "unverified", "medium"),
    "doorbell_family": ("FAMILY_VISITOR", "grounded", "unverified", "medium"),
    "doorbell_unknown": ("UNKNOWN_VISITOR", "generic", "unverified", "medium"),
    "motion_only": ("MOTION_ANOMALY", "generic", "no_claim", "low"),
    "motion_night": ("MOTION_ANOMALY", "generic", "no_claim", "low"),
}

WINDOWS = {
    "pharmacy": ("ding", "pharmacy refill", "2026-09-15T09:00:00Z", "2026-09-15T10:30:00Z"),
    "package": ("ding", "amazon package", "2026-09-15T09:00:00Z", "2026-09-15T10:30:00Z"),
    "family": ("ding", "family visit", "2026-09-15T09:00:00Z", "2026-09-15T10:30:00Z"),
    "police": ("ding", "police patrol", "2026-09-15T09:00:00Z", "2026-09-15T10:30:00Z"),
    "utility": ("ding", "utility meter check", "2026-09-15T09:00:00Z", "2026-09-15T10:30:00Z"),
}
WINDOW_CATEGORY = {"pharmacy": "MED_DELIVERY", "package": "PACKAGE_DELIVERY", "family": "FAMILY_VISITOR"}

CLAIMS = {
    "police": (["police", "officer"], "UNKNOWN_VISITOR", "high"),
    "utility": (["utility", "power company"], "UNKNOWN_VISITOR", "high"),
    "package": (["package", "courier"], "PACKAGE_DELIVERY", "medium"),
    "family": (["family", "guest"], "FAMILY_VISITOR", "medium"),
}

HINT_CASES = [
    ("medicine", ["medicine"], "MED_DELIVERY", "unverified", "high"),
    ("doctor", ["doctor"], "MED_DELIVERY", "unverified", "high"),
    ("package", ["package"], "PACKAGE_DELIVERY", "unverified", "medium"),
    ("courier", ["courier"], "PACKAGE_DELIVERY", "unverified", "medium"),
    ("guest", ["guest"], "FAMILY_VISITOR", "unverified", "medium"),
    ("relative", ["relative"], "FAMILY_VISITOR", "unverified", "medium"),
]

MEMORY_CASES = [
    ("leave_at_door", "MED_DELIVERY", "leave_at_door"),
    ("coming", "MED_DELIVERY", "coming"),
    ("waiting_for_parent", "MED_DELIVERY", "waiting_for_parent"),
    ("leave_at_door", "UNKNOWN_VISITOR", ""),
]


def synth(kind="button_press", tags=(), hint="", snapshot=False):
    payload = json.loads(json.dumps(BASE))
    payload["meta"]["time"] = TS
    payload["meta"]["request_id"] = f"eval-{uuid.uuid4().hex}"
    attributes = payload["data"]["attributes"]
    attributes["timestamp"] = TS_MS
    attributes["tags"] = list(tags)
    attributes["label_hint"] = hint
    payload["data"]["type"] = kind
    payload["data"]["id"] = f"ring_doorbell_01_{kind}_{TS_MS}"
    if snapshot:
        payload["snapshot_url"] = "https://example.invalid/snapshot.jpg"
    return payload


def strip_hints(payload: dict) -> dict:
    payload = json.loads(json.dumps(payload))
    attributes = payload["data"]["attributes"]
    attributes.pop("tags", None)
    attributes.pop("label_hint", None)
    payload.pop("snapshot_url", None)
    return payload


def case(case_id, payload, category, grounding, verification="no_claim", risk="low", memory="", window=None):
    return {
        "id": case_id,
        "payload": payload,
        "category": category,
        "grounding": grounding,
        "verification": verification,
        "risk": risk,
        "memory": memory,
        "window": window,
    }


def build_cases() -> list[dict]:
    cases = []
    for name, (category, grounding, verification, risk) in FIXTURES.items():
        payload = json.loads((ROOT / "mock" / "events" / f"{name}.json").read_text(encoding="utf-8"))
        cases.append(case(f"fixture:{name}", payload, category, grounding, verification, risk))
        stripped_category = "MOTION_ANOMALY" if category == "MOTION_ANOMALY" else "UNKNOWN_VISITOR"
        cases.append(case(f"stripped:{name}", strip_hints(payload), stripped_category, "generic"))
    for claim, (tags, category, unverified_risk) in CLAIMS.items():
        grounding = "generic" if category == "UNKNOWN_VISITOR" else "grounded"
        cases.append(case(f"claim:{claim}:none", synth(tags=tags), category, grounding, "unverified", unverified_risk))
        cases.append(case(f"claim:{claim}:snapshot", synth(tags=tags, snapshot=True), category, grounding, "verified", "low"))
        cases.append(
            case(f"claim:{claim}:window", synth(tags=tags), category, grounding, "verified", "low", window=WINDOWS[claim])
        )
        cases.append(
            case(f"claim:{claim}:window_other", synth(tags=tags), "MED_DELIVERY", "grounded", "contradiction", "high", window=WINDOWS["pharmacy"])
        )
    for name, category in WINDOW_CATEGORY.items():
        cases.append(case(f"window:{name}", synth(), category, "grounded", "no_claim", "low", window=WINDOWS[name]))
    for name, tags, category, verification, risk in HINT_CASES:
        cases.append(case(f"hint:{name}", synth(tags=tags), category, "grounded", verification, risk))
    for action, prior_category, expected_memory in MEMORY_CASES:
        cases.append(
            {
                "id": f"memory:{action}:prior={prior_category}",
                "payload": synth(tags=["medicine"]),
                "category": "MED_DELIVERY",
                "grounding": "grounded",
                "verification": "unverified",
                "risk": "high",
                "memory": expected_memory,
                "window": None,
                "prior": {"action": action, "category": prior_category},
            }
        )
    cases.append(case("memory:no_prior", synth(tags=["medicine"]), "MED_DELIVERY", "grounded", "unverified", "high"))
    return cases


def run_case(case_row: dict) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        database = Database(f"sqlite:///{Path(tmp) / 'eval.db'}")
        database.init_schema()
        if case_row.get("window"):
            database.add_expected_context(*case_row["window"])
        if case_row.get("prior"):
            prior_id = database.insert_event("eval", DEVICE, "button_press", TS, {"meta": {}})
            database.update_triage(prior_id, {"category": case_row["prior"]["category"]}, status="enriched")
            database.add_label(prior_id, f"device:{DEVICE}", case_row["prior"]["action"], source="eval")
        pipeline = EnrichmentPipeline(database, StubLLM())
        parsed = parse_ring_payload(case_row["payload"])
        event_id = database.insert_event(
            "eval", parsed["device_id"], parsed["kind"], parsed["occurred_at"], case_row["payload"]
        )
        result, ok = pipeline.enrich(database.get_event(event_id))
        database.close()
    expected_challenge = case_row["verification"] in {"unverified", "contradiction"}
    row = {
        "id": case_row["id"],
        "ok": ok,
        "category": result.category.value,
        "expected_category": case_row["category"],
        "grounding": result.grounding,
        "expected_grounding": case_row["grounding"],
        "verification_status": result.verification_status,
        "expected_verification": case_row["verification"],
        "risk_level": result.risk_level,
        "expected_risk": case_row["risk"],
        "memory_action": result.memory_action,
        "expected_memory": case_row["memory"],
    }
    row["checks"] = {
        "category": row["category"] == row["expected_category"],
        "grounding": row["grounding"] == row["expected_grounding"],
        "verification": row["verification_status"] == row["expected_verification"],
        "risk": row["risk_level"] == row["expected_risk"],
        "memory": row["memory_action"] == row["expected_memory"],
        "challenge": bool(result.challenge_question_en) == expected_challenge,
    }
    row["passed"] = all(row["checks"].values())
    return row


def summarise(rows: list[dict]) -> dict:
    categories = sorted({row["expected_category"] for row in rows})
    per_category = {}
    for category in categories:
        tp = sum(row["category"] == category and row["expected_category"] == category for row in rows)
        fp = sum(row["category"] == category and row["expected_category"] != category for row in rows)
        fn = sum(row["category"] != category and row["expected_category"] == category for row in rows)
        per_category[category] = {
            "support": tp + fn,
            "precision": round(tp / (tp + fp), 3) if tp + fp else 1.0,
            "recall": round(tp / (tp + fn), 3) if tp + fn else 1.0,
        }
    claim_rows = [row for row in rows if row["expected_verification"] != "no_claim"]
    memory_rows = [row for row in rows if row["id"].startswith("memory:")]
    return {
        "cases": len(rows),
        "passed": sum(row["passed"] for row in rows),
        "category_accuracy": round(sum(row["checks"]["category"] for row in rows) / len(rows), 3),
        "gatekeeper_accuracy": round(
            sum(row["checks"]["verification"] and row["checks"]["risk"] for row in claim_rows) / len(claim_rows), 3
        ),
        "memory_accuracy": round(sum(row["checks"]["memory"] for row in memory_rows) / len(memory_rows), 3),
        "demotions": sum(row["grounding"] == "demoted_insufficient_evidence" for row in rows),
        "per_category": per_category,
        "failures": [row["id"] for row in rows if not row["passed"]],
    }


def render(summary: dict, rows: list[dict]) -> str:
    lines = [
        f"AccessBell triage eval - {summary['cases']} scenario cases"
        " (fixture-derived labels, not production telemetry)",
        "",
        f"cases passed          {summary['passed']}/{summary['cases']}",
        f"category accuracy     {summary['category_accuracy']}",
        f"gatekeeper accuracy   {summary['gatekeeper_accuracy']}",
        f"memory accuracy       {summary['memory_accuracy']}",
        f"demotions             {summary['demotions']}",
        "",
        f"{'category':<18}{'support':>8}{'precision':>11}{'recall':>8}",
    ]
    for category, stats in summary["per_category"].items():
        lines.append(f"{category:<18}{stats['support']:>8}{stats['precision']:>11}{stats['recall']:>8}")
    if summary["failures"]:
        lines.append("")
        lines.append("failed cases:")
        for row in rows:
            if not row["passed"]:
                failed = [name for name, ok in row["checks"].items() if not ok]
                lines.append(f"  {row['id']}: {', '.join(failed)}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    rows = [run_case(case_row) for case_row in build_cases()]
    summary = summarise(rows)
    if args.json:
        print(json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False))
    else:
        print(render(summary, rows))
    return 0 if summary["passed"] == summary["cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
