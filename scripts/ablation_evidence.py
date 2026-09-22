"""Evidence ablation: how much does grounding signal contribute?

Runs the same fixtures under three arms so the grounding gate is measurable:
  event_only       -> payload hints stripped, no expected window
  payload_hints    -> fixtures as shipped (demo label hints)
  expected_window  -> hints stripped, expected window added

Usage: python scripts/ablation_evidence.py [--json]
Fixture-derived, not production telemetry.
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db import Database
from backend.llm.stub import StubLLM
from backend.triage import EnrichmentPipeline
from backend.webhook import parse_ring_payload

ARMS = ("event_only", "payload_hints", "expected_window")

EXPECTED_WINDOWS = {
    "doorbell_med": ("ding", "pharmacy refill", "2026-09-15T09:00:00Z", "2026-09-15T10:30:00Z"),
    "doorbell_package_window": ("ding", "amazon package", "2026-09-15T13:00:00Z", "2026-09-15T16:00:00Z"),
    "doorbell_family": ("ding", "family visit", "2026-09-15T17:00:00Z", "2026-09-15T20:00:00Z"),
}

TARGETS = {
    "doorbell_med": "MED_DELIVERY",
    "doorbell_package_window": "PACKAGE_DELIVERY",
    "doorbell_family": "FAMILY_VISITOR",
    "doorbell_unknown": "UNKNOWN_VISITOR",
    "motion_only": "MOTION_ANOMALY",
    "motion_night": "MOTION_ANOMALY",
}


def strip_hints(raw: dict) -> dict:
    raw = json.loads(json.dumps(raw))
    meta = raw.get("meta")
    if isinstance(meta, dict):
        meta.pop("tags", None)
        meta.pop("label_hint", None)
    attributes = ((raw.get("data") or {}).get("attributes")) if isinstance(raw.get("data"), dict) else None
    if isinstance(attributes, dict):
        attributes.pop("tags", None)
        attributes.pop("label_hint", None)
    return raw


def run(events_dir=None) -> dict:
    events_dir = Path(events_dir) if events_dir else ROOT / "mock" / "events"
    report = {"source": "fixture-derived, not production telemetry", "arms": {}, "rows": []}
    for arm in ARMS:
        correct = 0
        for name, target in TARGETS.items():
            with tempfile.TemporaryDirectory() as tmp:
                database = Database(f"sqlite:///{Path(tmp) / 'ablation.db'}")
                database.init_schema()
                pipeline = EnrichmentPipeline(database, StubLLM())
                payload = json.loads((events_dir / f"{name}.json").read_text(encoding="utf-8"))
                if arm == "event_only":
                    payload = strip_hints(payload)
                if arm == "expected_window":
                    payload = strip_hints(payload)
                    if name in EXPECTED_WINDOWS:
                        database.add_expected_context(*EXPECTED_WINDOWS[name])
                parsed = parse_ring_payload(payload)
                event_id = database.insert_event(
                    "ablation", parsed["device_id"], parsed["kind"], parsed["occurred_at"], payload
                )
                result, ok = pipeline.enrich(database.get_event(event_id))
                match = bool(ok and result.category.value == target)
                correct += 1 if match else 0
                report["rows"].append(
                    {
                        "arm": arm,
                        "fixture": name,
                        "category": result.category.value,
                        "grounding": result.grounding,
                        "target": target,
                        "match": match,
                    }
                )
                database.close()
        report["arms"][arm] = round(correct / len(TARGETS), 3)
    return report


def render(report: dict) -> str:
    lines = [f"{'arm':<16}{'accuracy':>10}"]
    for arm in ARMS:
        lines.append(f"{arm:<16}{report['arms'][arm]:>10}")
    lines.append("")
    lines.append(f"{'fixture':<28}{'event_only':>12}{'payload_hints':>15}{'expected_window':>17}")
    by_fixture = {}
    for row in report["rows"]:
        by_fixture.setdefault(row["fixture"], {})[row["arm"]] = row
    for fixture in TARGETS:
        cells = []
        for arm in ARMS:
            row = by_fixture.get(fixture, {}).get(arm)
            cells.append("ok" if row and row["match"] else "miss")
        lines.append(f"{fixture:<28}{cells[0]:>12}{cells[1]:>15}{cells[2]:>17}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = run()
    print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())