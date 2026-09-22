import asyncio
import json
import time

from backend.calendar_mcp import build_calendar_client
from backend.config import Settings
from backend.llm.stub import StubLLM
from backend.metrics import Metrics
from backend.triage import EnrichmentPipeline, Tier1Rules


class CountingLLM:
    def __init__(self):
        self.calls = 0

    def triage(self, **kwargs):
        self.calls += 1
        return {}


class SlowCalendar:
    def list_events(self, occurred_at):
        time.sleep(0.05)
        return []


class LateCalendar:
    def list_events(self, occurred_at):
        time.sleep(0.02)
        return [{"title": "Pharmacy delivery"}]


class FailingCalendar:
    def list_events(self, occurred_at):
        raise RuntimeError("calendar down")


def _event(occurred_at="2026-09-15T10:00:00Z", kind="ding"):
    return dict(
        id=1,
        kind=kind,
        device_id="d1",
        occurred_at=occurred_at,
        raw_json=json.dumps({"meta": {}}),
        triage_json="{}",
    )


def test_enrich_budget_times_out_to_tier1(monkeypatch):
    import backend.main as main_module

    class SlowPipeline:
        def enrich(self, event):
            time.sleep(0.4)
            raise AssertionError("enrich should have been bounded by ENRICH_BUDGET_MS")

    monkeypatch.setattr(main_module, "pipeline", SlowPipeline())
    monkeypatch.setattr(main_module.settings, "enrich_budget_ms", 30)
    event = {"id": 1, "kind": "ding", "device_id": "d1", "occurred_at": "2026-09-15T10:00:00Z", "raw_json": "{}"}
    result, ok = asyncio.run(main_module._run_enrichment(event))
    assert ok is False
    assert result.category.value == "UNKNOWN_VISITOR"


def test_tier1_rules_do_not_touch_the_llm():
    llm = CountingLLM()
    result = Tier1Rules().classify("button_press")
    assert result.category.value == "UNKNOWN_VISITOR"
    assert llm.calls == 0


def test_calendar_client_timeout_follows_budget(monkeypatch):
    monkeypatch.setenv("CALENDAR_MCP_URL", "http://cal.test/mcp")
    monkeypatch.setenv("CONTEXT_BUDGET_MS", "150")
    client = build_calendar_client(Settings())
    assert client._timeout == 0.15


def test_context_budget_marks_timeout_and_records_metric(db):
    metrics = Metrics()
    pipeline = EnrichmentPipeline(
        db, StubLLM(), calendar=SlowCalendar(), metrics=metrics, context_budget_ms=1
    )
    result, ok = pipeline.enrich(_event())
    assert ok is True
    assert result.context_status == "timeout"
    assert metrics.snapshot()["timers"]["context_ms"]["count"] == 1


def test_late_calendar_result_is_discarded(db):
    pipeline = EnrichmentPipeline(db, StubLLM(), calendar=LateCalendar(), context_budget_ms=1)
    result, ok = pipeline.enrich(_event())
    assert ok is True
    assert result.context_status == "timeout"
    assert not any(item.startswith("calendar") for item in result.evidence)


def test_calendar_failure_fails_open(db):
    pipeline = EnrichmentPipeline(db, StubLLM(), calendar=FailingCalendar())
    result, ok = pipeline.enrich(_event())
    assert ok is True
    assert result.context_status == "timeout"
    assert result.category.value == "UNKNOWN_VISITOR"


def test_context_status_disabled_without_calendar(db):
    result, ok = EnrichmentPipeline(db, StubLLM()).enrich(_event())
    assert ok is True
    assert result.context_status == "disabled"