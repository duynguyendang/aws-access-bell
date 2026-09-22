import json
import time
from enum import Enum

from pydantic import BaseModel, Field, field_validator
from pydantic import ValidationError

from .captions import TIER1 as TIER1_CAPTIONS
from .captions import generic_captions, quiet_captions
from .util import is_quiet_hours
from .webhook import extract_payload_hints

KNOWN_EVIDENCE_SOURCES = frozenset(
    {"doorbell", "motion", "expected_context", "calendar", "time_pattern", "user_label", "snapshot"}
)


class Category(str, Enum):
    MED_DELIVERY = "MED_DELIVERY"
    PACKAGE_DELIVERY = "PACKAGE_DELIVERY"
    FAMILY_VISITOR = "FAMILY_VISITOR"
    UNKNOWN_VISITOR = "UNKNOWN_VISITOR"
    MOTION_ANOMALY = "MOTION_ANOMALY"


class TriageResult(BaseModel):
    category: Category
    urgency: int = Field(ge=0, le=10)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    caption_en: str
    caption_vi: str = ""
    suggested_replies: list[str] = Field(default_factory=lambda: ["leave_at_door", "coming", "not_now"])
    do_not_invent: bool = Field(default=True)
    grounding: str = Field(default="grounded")
    context_status: str = Field(default="disabled")

    @field_validator("evidence")
    @classmethod
    def _evidence_known(cls, values: list[str]) -> list[str]:
        for value in values:
            source = value.split(":", 1)[0]
            if source not in KNOWN_EVIDENCE_SOURCES:
                raise ValueError(f"unknown evidence source: {source!r}")
        return values

    @field_validator("caption_en")
    @classmethod
    def _caption_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("caption_en must not be empty")
        return value


KIND_TIER1 = {
    kind: (Category(entry["category"]), entry["en"], entry["vi"])
    for kind, entry in TIER1_CAPTIONS.items()
}


class Tier1Rules:
    def classify(self, kind: str) -> TriageResult:
        key = (kind or "motion").lower()
        category, en, vi = KIND_TIER1.get(key, KIND_TIER1["motion"])
        evidence = ["doorbell"] if ("ding" in key or "button_press" in key) else ["motion"]
        return TriageResult(
            category=category,
            urgency=4,
            confidence=0.6,
            evidence=evidence,
            caption_en=en,
            caption_vi=vi,
            suggested_replies=["leave_at_door", "coming", "not_now"],
            grounding="generic",
        )


class EnrichmentPipeline:
    def __init__(self, db, llm, calendar=None, metrics=None, context_budget_ms: int = 200, quiet_hours=None):
        self._db = db
        self._llm = llm
        self._calendar = calendar
        self._metrics = metrics
        self._context_budget_ms = context_budget_ms
        self._quiet_hours = quiet_hours
        self._rules = Tier1Rules()

    def enrich(self, event: dict) -> tuple[TriageResult, bool]:
        try:
            raw = json.loads(event.get("raw_json") or "{}")
        except (TypeError, ValueError):
            raw = {}
        expected = self._db.list_active_expected_context(event["occurred_at"])
        labels = self._db.labels_for_device(event.get("device_id") or "")
        calendar, context_status = self._join_calendar(event["occurred_at"])
        try:
            payload = self._llm.triage(
                kind=event["kind"],
                device_id=event.get("device_id") or "",
                occurred_at=event["occurred_at"],
                raw=raw,
                expected=expected,
                labels=labels,
                calendar=calendar,
            )
        except Exception:
            fallback = self._rules.classify(event["kind"])
            fallback.context_status = context_status
            return fallback, False
        try:
            result = TriageResult.model_validate(payload)
        except ValidationError:
            fallback = self._rules.classify(event["kind"])
            fallback.context_status = context_status
            return fallback, False
        result = self._apply_guardrails(result)
        result.context_status = context_status
        if not self._sanity(result, expected, raw):
            result = self._demote(result, event["kind"])
            result.context_status = context_status
        return self._apply_quiet_hours(result, event["occurred_at"]), True

    def _join_calendar(self, occurred_at: str) -> tuple[list[dict], str]:
        if self._calendar is None:
            return [], "disabled"
        started = time.perf_counter()
        status = "ok"
        try:
            events = self._calendar.list_events(occurred_at)
        except Exception:
            events, status = [], "timeout"
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if self._metrics is not None:
            self._metrics.observe("context_ms", elapsed_ms)
        if status == "ok" and self._context_budget_ms and elapsed_ms > self._context_budget_ms:
            return [], "timeout"
        return events, status

    def _apply_quiet_hours(self, result: TriageResult, occurred_at: str) -> TriageResult:
        if not self._quiet_hours:
            return result
        start, end = self._quiet_hours
        if not is_quiet_hours(occurred_at, start, end):
            return result
        quiet = quiet_captions(result.category.value)
        if quiet:
            result.caption_en = quiet["en"]
            result.caption_vi = quiet["vi"]
        return result

    @staticmethod
    def _apply_guardrails(result: TriageResult) -> TriageResult:
        captions = generic_captions(result.category.value)
        if captions:
            result.caption_en = captions["en"]
            result.caption_vi = captions["vi"]
            result.do_not_invent = True
            if result.grounding == "grounded":
                result.grounding = "generic"
        return result

    def _demote(self, result: TriageResult, kind: str) -> TriageResult:
        fallback = self._rules.classify(kind)
        fallback.evidence = result.evidence
        fallback.confidence = result.confidence
        fallback.do_not_invent = True
        fallback.grounding = "demoted_insufficient_evidence"
        return fallback

    @staticmethod
    def _sanity(result: TriageResult, expected: list[dict], raw: dict) -> bool:
        if result.category in {Category.UNKNOWN_VISITOR, Category.MOTION_ANOMALY}:
            return True
        evidence_grounded = any(
            evidence.startswith(("expected_context", "user_label", "snapshot", "calendar"))
            for evidence in result.evidence
        )
        tags, label_hint = extract_payload_hints(raw)
        payload_grounded = bool(tags or label_hint)
        if not (evidence_grounded or payload_grounded):
            return False
        return result.confidence >= 0.6 or bool(expected)

    @staticmethod
    def parse_payload(payload: dict) -> TriageResult:
        return TriageResult.model_validate(payload)