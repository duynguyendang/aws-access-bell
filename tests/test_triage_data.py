import json
from pathlib import Path

import pytest

from backend.db import Database
from backend.llm.stub import StubLLM
from backend.triage import EnrichmentPipeline

DATA = json.loads((Path(__file__).parent / "data" / "triage_cases.json").read_text(encoding="utf-8"))
CASES = DATA["cases"]


@pytest.fixture
def pipeline(tmp_path):
    database = Database(str(tmp_path / "cases.db"))
    database.init_schema()
    yield database
    database.close()


class FakeCalendar:
    def __init__(self, events):
        self._events = events

    def list_events(self, occurred_at):
        return self._events


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_triage_requirement_cases(pipeline, case):
    database = pipeline
    for expected in case["expected_context"]:
        database.add_expected_context(
            expected["kind"], expected["label"], expected["window_start"], expected["window_end"]
        )
    chain = EnrichmentPipeline(database, StubLLM(), calendar=FakeCalendar(case.get("calendar", [])))
    ev = case["event"]
    event_id = database.insert_event("test", ev["device_id"], ev["kind"], ev["occurred_at"], ev["raw"])
    result, ok = chain.enrich(database.get_event(event_id))
    expect = case["expect"]

    assert ok is True, case["summary"]
    assert result.category.value == expect["category"]
    assert 0 <= result.confidence <= 1
    assert 0 <= result.urgency <= 10

    for prefix in expect.get("evidence_prefix", []):
        assert any(e.startswith(prefix) for e in result.evidence), result.evidence
    if "urgency_min" in expect:
        assert result.urgency >= expect["urgency_min"]
    if "urgency_max" in expect:
        assert result.urgency <= expect["urgency_max"]

    assert result.caption_en.strip()
    if expect.get("require_caption_vi"):
        assert result.caption_vi.strip()
    if expect.get("generic_caption"):
        assert result.caption_en == "Someone is at the door"
        assert result.do_not_invent is True