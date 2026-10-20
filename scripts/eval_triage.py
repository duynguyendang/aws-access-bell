"""Labeled triage eval: category, Gatekeeper, memory, grounding demotion and escalation.

Scenarios are fixture-derived; the expected labels are written by hand in this
file (synthetic scenario labels, not human-reviewed production data). Escalation
is scored as if the resident had opted in (enabled, min_urgency 7); consent stays
off by default in the product.

Usage: python scripts/eval_triage.py [--json] [--provider stub|bedrock|...] [--model ID]
Exits non-zero when any case fails.
"""

import argparse
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db import Database
from backend.escalation import escalation_triggered
from backend.llm.stub import StubLLM
from backend.triage import EnrichmentPipeline
from backend.webhook import parse_ring_payload

TS = "2026-09-15T09:45:00Z"
TS_MS = 1789465500000
DEVICE = "ring_doorbell_01"

BASE = json.loads((ROOT / "mock" / "events" / "doorbell_unknown.json").read_text(encoding="utf-8"))

FIXTURES = {
    "doorbell_med": ("MED_DELIVERY", "grounded", "unverified", "high", True),
    "doorbell_package_window": ("PACKAGE_DELIVERY", "grounded", "unverified", "medium", False),
    "doorbell_family": ("FAMILY_VISITOR", "grounded", "unverified", "medium", False),
    "doorbell_unknown": ("UNKNOWN_VISITOR", "generic", "no_claim", "low", False),
    "motion_only": ("MOTION_ANOMALY", "generic", "no_claim", "low", False),
    "motion_night": ("MOTION_ANOMALY", "generic", "no_claim", "low", False),
}

WINDOWS = {
    "pharmacy": ("ding", "pharmacy refill", "2026-09-15T09:00:00Z", "2026-09-15T10:30:00Z"),
    "package": ("ding", "amazon package", "2026-09-15T09:00:00Z", "2026-09-15T10:30:00Z"),
    "family": ("ding", "family visit", "2026-09-15T09:00:00Z", "2026-09-15T10:30:00Z"),
    "police": ("ding", "police patrol", "2026-09-15T09:00:00Z", "2026-09-15T10:30:00Z"),
    "utility": ("ding", "utility meter check", "2026-09-15T09:00:00Z", "2026-09-15T10:30:00Z"),
}
WINDOW_CATEGORY = {
    "pharmacy": ("MED_DELIVERY", True),
    "package": ("PACKAGE_DELIVERY", False),
    "family": ("FAMILY_VISITOR", False),
}

CLAIMS = {
    "police": ("I am a police officer. Please open the door.", "UNKNOWN_VISITOR", "high"),
    "utility": ("I am from the power company. I need to check the meter.", "UNKNOWN_VISITOR", "high"),
    "package": ("I have a package delivery for you.", "PACKAGE_DELIVERY", "medium"),
    "family": ("Hi, it is your family visiting.", "FAMILY_VISITOR", "medium"),
}

HINT_CASES = [
    ("medicine", ["medicine"], "MED_DELIVERY", "unverified", "high", True),
    ("doctor", ["doctor"], "MED_DELIVERY", "unverified", "high", True),
    ("package", ["package"], "PACKAGE_DELIVERY", "unverified", "medium", False),
    ("courier", ["courier"], "PACKAGE_DELIVERY", "unverified", "medium", False),
    ("guest", ["guest"], "FAMILY_VISITOR", "no_claim", "low", False),
    ("relative", ["relative"], "FAMILY_VISITOR", "unverified", "medium", False),
]


class InventingLLM:
    def __init__(self, payload):
        self._payload = payload

    def triage(self, **kwargs):
        return dict(self._payload)


def invented(caption_en: str, category: str, urgency: int) -> InventingLLM:
    return InventingLLM(
        {
            "category": category,
            "urgency": urgency,
            "confidence": 0.95,
            "evidence": ["doorbell"],
            "caption_en": caption_en,
            "caption_vi": "",
        }
    )


DEMOTION_CASES = [
    ("family_alex", "Your friend Alex is at the door", "FAMILY_VISITOR", 3, "Alex"),
    ("med_pharmacy", "Pharmacy delivery for Sarah", "MED_DELIVERY", 8, "Sarah"),
    ("package_courier", "Courier with your parcel", "PACKAGE_DELIVERY", 6, "Courier with your parcel"),
]

MEMORY_CASES = [
    ("leave_at_door", "MED_DELIVERY", "leave_at_door"),
    ("coming", "MED_DELIVERY", "coming"),
    ("waiting_for_parent", "MED_DELIVERY", "waiting_for_parent"),
    ("leave_at_door", "UNKNOWN_VISITOR", ""),
]


def synth(kind="button_press", tags=(), hint="", statement="", snapshot=False):
    payload = json.loads(json.dumps(BASE))
    payload["meta"]["time"] = TS
    payload["meta"]["request_id"] = f"eval-{uuid.uuid4().hex}"
    attributes = payload["data"]["attributes"]
    attributes["timestamp"] = TS_MS
    attributes["tags"] = list(tags)
    attributes["label_hint"] = hint
    if statement:
        attributes["visitor_statement"] = statement
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
    attributes.pop("visitor_statement", None)
    payload.pop("snapshot_url", None)
    return payload


def case(
    case_id,
    payload,
    category,
    grounding,
    verification="no_claim",
    risk="low",
    memory="",
    window=None,
    llm=None,
    forbid="",
    escalate=False,
    prior=None,
):
    return {
        "id": case_id,
        "payload": payload,
        "category": category,
        "grounding": grounding,
        "verification": verification,
        "risk": risk,
        "memory": memory,
        "window": window,
        "llm": llm,
        "forbid": forbid,
        "escalate": escalate,
        "prior": prior,
    }


def build_cases() -> list[dict]:
    cases = []
    for name, (category, grounding, verification, risk, escalate) in FIXTURES.items():
        payload = json.loads((ROOT / "mock" / "events" / f"{name}.json").read_text(encoding="utf-8"))
        cases.append(
            case(f"fixture:{name}", payload, category, grounding, verification, risk, escalate=escalate)
        )
        stripped_category = "MOTION_ANOMALY" if category == "MOTION_ANOMALY" else "UNKNOWN_VISITOR"
        cases.append(case(f"stripped:{name}", strip_hints(payload), stripped_category, "generic"))
    for claim, (statement, category, unverified_risk) in CLAIMS.items():
        high_stakes = unverified_risk == "high"
        grounding = "generic" if category == "UNKNOWN_VISITOR" else "grounded"
        cases.append(
            case(
                f"claim:{claim}:none",
                synth(statement=statement),
                category,
                grounding,
                "unverified",
                unverified_risk,
                escalate=high_stakes,
            )
        )
        cases.append(
            case(
                f"claim:{claim}:snapshot",
                synth(statement=statement, snapshot=True),
                category,
                grounding,
                "unverified",
                unverified_risk,
                escalate=high_stakes,
            )
        )
        cases.append(
            case(
                f"claim:{claim}:window",
                synth(statement=statement),
                category,
                grounding,
                "verified",
                "low",
                window=WINDOWS[claim],
            )
        )
        is_contradiction = claim in {"police", "utility", "government"}
        if is_contradiction:
            other_window, other_category = "pharmacy", "MED_DELIVERY"
        elif claim == "package":
            other_window, other_category = "family", "FAMILY_VISITOR"
        else:
            other_window, other_category = "package", "PACKAGE_DELIVERY"
        cases.append(
            case(
                f"claim:{claim}:window_other",
                synth(statement=statement),
                other_category,
                "grounded",
                "contradiction" if is_contradiction else "unverified",
                "high" if is_contradiction else unverified_risk,
                window=WINDOWS[other_window],
                escalate=is_contradiction,
            )
        )
    for name, (category, escalate) in WINDOW_CATEGORY.items():
        cases.append(
            case(f"window:{name}", synth(), category, "grounded", "no_claim", "low", window=WINDOWS[name], escalate=escalate)
        )
    for name, tags, category, verification, risk, escalate in HINT_CASES:
        cases.append(
            case(f"hint:{name}", synth(tags=tags), category, "grounded", verification, risk, escalate=escalate)
        )
    cases.append(
        case(
            "claim:police:prior_label",
            synth(statement="I am a police officer. Please open the door."),
            "UNKNOWN_VISITOR",
            "generic",
            "unverified",
            "high",
            escalate=True,
            prior={"action": "coming", "category": "UNKNOWN_VISITOR", "label": "police"},
        )
    )
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
                "llm": None,
                "forbid": "",
                "escalate": True,
            }
        )
    cases.append(
        case("memory:no_prior", synth(tags=["medicine"]), "MED_DELIVERY", "grounded", "unverified", "high", escalate=True)
    )
    for name, caption, category, urgency, forbid in DEMOTION_CASES:
        cases.append(
            case(
                f"demote:{name}",
                synth(),
                "UNKNOWN_VISITOR",
                "demoted_insufficient_evidence",
                "no_claim",
                "low",
                llm=invented(caption, category, urgency),
                forbid=forbid,
            )
        )
    return cases


def run_case(case_row: dict, llm) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        database = Database(f"sqlite:///{Path(tmp) / 'eval.db'}")
        database.init_schema()
        if case_row.get("window"):
            database.add_expected_context(*case_row["window"])
        if case_row.get("prior"):
            prior_id = database.insert_event("eval", DEVICE, "button_press", TS, {"meta": {}})
            database.update_triage(prior_id, {"category": case_row["prior"]["category"]}, status="enriched")
            database.add_label(
                prior_id,
                f"device:{DEVICE}",
                case_row["prior"].get("label") or case_row["prior"]["action"],
                source="eval",
            )
        pipeline = EnrichmentPipeline(database, case_row.get("llm") or llm)
        parsed = parse_ring_payload(case_row["payload"])
        event_id = database.insert_event(
            "eval", parsed["device_id"], parsed["kind"], parsed["occurred_at"], case_row["payload"]
        )
        result, ok = pipeline.enrich(database.get_event(event_id))
        database.close()
    forbid = case_row.get("forbid") or ""
    expected_challenge = case_row["verification"] in {"unverified", "contradiction"}
    escalation_armed = escalation_triggered(
        {
            "urgency": result.urgency,
            "risk_level": result.risk_level,
            "verification_status": result.verification_status,
        },
        {"enabled": True, "min_urgency": 7},
    )
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
        "urgency": result.urgency,
        "caption_en": result.caption_en,
        "escalation_armed": escalation_armed,
        "expected_escalation": bool(case_row.get("escalate")),
    }
    row["checks"] = {
        "category": row["category"] == row["expected_category"],
        "grounding": row["grounding"] == row["expected_grounding"],
        "verification": row["verification_status"] == row["expected_verification"],
        "risk": row["risk_level"] == row["expected_risk"],
        "memory": row["memory_action"] == row["expected_memory"],
        "challenge": bool(result.challenge_question_en) == expected_challenge,
        "no_invented": (forbid not in result.caption_en) if forbid else True,
        "escalation": row["escalation_armed"] == row["expected_escalation"],
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
    escalation = {
        "expected": sum(row["expected_escalation"] for row in rows),
        "armed": sum(row["escalation_armed"] for row in rows),
        "false": sum(row["escalation_armed"] and not row["expected_escalation"] for row in rows),
        "missed": sum(row["expected_escalation"] and not row["escalation_armed"] for row in rows),
    }
    escalation["false_rate"] = (
        round(escalation["false"] / escalation["armed"], 3) if escalation["armed"] else 0.0
    )
    escalation["missed_rate"] = (
        round(escalation["missed"] / escalation["expected"], 3) if escalation["expected"] else 0.0
    )
    return {
        "cases": len(rows),
        "passed": sum(row["passed"] for row in rows),
        "category_accuracy": round(sum(row["checks"]["category"] for row in rows) / len(rows), 3),
        "gatekeeper_accuracy": round(
            sum(row["checks"]["verification"] and row["checks"]["risk"] for row in claim_rows) / len(claim_rows), 3
        ),
        "memory_accuracy": round(sum(row["checks"]["memory"] for row in memory_rows) / len(memory_rows), 3),
        "demotions": sum(row["grounding"] == "demoted_insufficient_evidence" for row in rows),
        "escalation": escalation,
        "per_category": per_category,
        "failures": [row["id"] for row in rows if not row["passed"]],
    }


def render(summary: dict, rows: list[dict], provider: str, model: str) -> str:
    escalation = summary["escalation"]
    lines = [
        f"AccessBell triage eval - {summary['cases']} scenario cases",
        f"provider {provider}, model {model}; fixture-derived labels, not production telemetry",
        "escalation scored as if opted in (enabled, min_urgency 7); consent stays off by default",
        "",
        f"cases passed          {summary['passed']}/{summary['cases']}",
        f"category accuracy     {summary['category_accuracy']}",
        f"gatekeeper accuracy   {summary['gatekeeper_accuracy']}",
        f"memory accuracy       {summary['memory_accuracy']}",
        f"demotions             {summary['demotions']}",
        f"escalations armed     {escalation['armed']}/{escalation['expected']} expected"
        f" (false {escalation['false']}, missed {escalation['missed']})",
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


def build_llm_for(provider: str, model: str):
    if provider == "stub":
        return "stub", StubLLM()
    from backend.config import Settings
    from backend.llm import build_llm, resolve_model_name

    settings = Settings(llm_provider=provider, llm_model=model)
    return resolve_model_name(settings), build_llm(settings)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--provider", default=os.environ.get("LLM_PROVIDER", "stub"))
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL", ""))
    args = parser.parse_args()
    try:
        model_label, llm = build_llm_for(args.provider, args.model)
    except Exception as exc:
        print(f"cannot initialise provider {args.provider!r}: {exc}", file=sys.stderr)
        print("for Bedrock: pip install -r requirements-bedrock.txt and configure AWS credentials", file=sys.stderr)
        return 2
    rows = [run_case(case_row, llm) for case_row in build_cases()]
    summary = summarise(rows)
    if args.json:
        print(
            json.dumps(
                {"provider": args.provider, "model": model_label, "summary": summary, "rows": rows},
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(render(summary, rows, args.provider, model_label))
    return 0 if summary["passed"] == summary["cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
