import json
import re
import time
from enum import Enum

from pydantic import BaseModel, Field, field_validator
from pydantic import ValidationError

from .captions import CHALLENGE as CHALLENGE_TEXT
from .captions import CHALLENGE_BY_CLAIM, CLAIM as CLAIM_CAPTIONS
from .captions import CLAIM_VERIFIED
from .captions import MEMORY_ACTION as MEMORY_ACTION_LABELS
from .captions import MEMORY_BASIS as MEMORY_BASIS_TEMPLATES
from .captions import MEMORY_CATEGORY as MEMORY_CATEGORY_LABELS
from .captions import TIER1 as TIER1_CAPTIONS
from .captions import generic_captions, quiet_captions
from .util import is_quiet_hours
from .webhook import extract_payload_hints, extract_visitor_statement

KNOWN_EVIDENCE_SOURCES = frozenset(
    {"doorbell", "motion", "expected_context", "calendar", "time_pattern", "user_label", "visitor_statement"}
)

CLAIM_KEYWORDS = {
    "police": ["police", "officer", "cop"],
    "utility": ["utility", "power company", "electric company", "water company", "gas company", "power", "electric", "water"],
    "government": ["government", "city council", "official", "inspector"],
    "pharmacy": ["pharmacy", "medicine", "med", "prescription", "drug", "doctor"],
    "package": ["package", "delivery", "courier", "parcel", "shipment"],
    "family": ["family", "relative", "friend", "neighbor", "neighbour"],
}
HIGH_STAKES_CLAIMS = {"police", "utility", "government", "pharmacy"}
CONTRADICTION_CLAIMS = {"police", "utility", "government"}


def _challenge(claim: str) -> tuple[str, str]:
    text = CHALLENGE_BY_CLAIM.get(claim, CHALLENGE_TEXT)
    return text["en"], text["vi"]


REPLY_ACTIONS = {"leave_at_door", "coming", "not_now", "waiting_for_parent"}


def _text_matches_claim(text: str, claim: str) -> bool:
    lowered = (text or "").lower()
    return any(re.search(r"\b" + re.escape(kw) + r"\b", lowered) for kw in CLAIM_KEYWORDS.get(claim, []))


def extract_claim(raw: dict) -> str:
    """Return the canonical claim key from the visitor statement / payload hints, or ""."""
    tags, hint = extract_payload_hints(raw)
    statement = extract_visitor_statement(raw)
    text = " ".join(tags + [hint, statement]).lower()
    for claim in ("police", "utility", "government", "pharmacy", "package", "family"):
        if _text_matches_claim(text, claim):
            return claim
    return ""


def _scheduled_claims(expected, calendar) -> set[str]:
    claims = set()
    for window in expected or []:
        text = str(window.get("label") or "")
        for claim in CLAIM_KEYWORDS:
            if _text_matches_claim(text, claim):
                claims.add(claim)
    for item in calendar or []:
        text = str(item.get("title") or item.get("label") or "")
        for claim in CLAIM_KEYWORDS:
            if _text_matches_claim(text, claim):
                claims.add(claim)
    return claims


def verify_claim(raw: dict, expected, calendar) -> dict:
    """Verify a visitor claim against resident-created context only.

    A claim is verified only by an expected window or a calendar event the
    resident created. The visitor's own words, a previous user label, and an
    unanalysed snapshot are never proof of identity.
    """
    claim = extract_claim(raw)
    if not claim:
        return {
            "verification_status": "no_claim",
            "risk_level": "low",
            "claimed_identity": "",
            "challenge_question_en": "",
            "challenge_question_vi": "",
        }
    scheduled = _scheduled_claims(expected, calendar)
    if claim in scheduled:
        return {
            "verification_status": "verified",
            "risk_level": "low",
            "claimed_identity": claim,
            "challenge_question_en": "",
            "challenge_question_vi": "",
        }
    if claim in CONTRADICTION_CLAIMS and scheduled:
        challenge_en, challenge_vi = _challenge(claim)
        return {
            "verification_status": "contradiction",
            "risk_level": "high",
            "claimed_identity": claim,
            "challenge_question_en": challenge_en,
            "challenge_question_vi": challenge_vi,
        }
    challenge_en, challenge_vi = _challenge(claim)
    return {
        "verification_status": "unverified",
        "risk_level": "high" if claim in HIGH_STAKES_CLAIMS else "medium",
        "claimed_identity": claim,
        "challenge_question_en": challenge_en,
        "challenge_question_vi": challenge_vi,
    }


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
    # Gatekeeper (anti-scam): verification is an extra layer, never a
    # replacement for the evidence gate / demotion logic.
    verification_status: str = Field(default="no_claim")
    risk_level: str = Field(default="low")
    claimed_identity: str = Field(default="")
    challenge_question_en: str = Field(default="")
    challenge_question_vi: str = Field(default="")
    # Memory: same-as-last-time suggestion, only when the last reply for
    # this device had the same triage category as the current event.
    memory_action: str = Field(default="")
    memory_basis_en: str = Field(default="")
    memory_basis_vi: str = Field(default="")

    @field_validator("verification_status")
    @classmethod
    def _verification_known(cls, value: str) -> str:
        if value not in {"verified", "unverified", "no_claim", "contradiction"}:
            raise ValueError(f"unknown verification_status: {value!r}")
        return value

    @field_validator("risk_level")
    @classmethod
    def _risk_known(cls, value: str) -> str:
        if value not in {"low", "medium", "high"}:
            raise ValueError(f"unknown risk_level: {value!r}")
        return value

    @field_validator("memory_action")
    @classmethod
    def _memory_action_known(cls, value: str) -> str:
        if value and value not in REPLY_ACTIONS:
            raise ValueError(f"unknown memory_action: {value!r}")
        return value

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
            return self._apply_verification_and_memory(
                fallback, raw, expected, calendar, event.get("device_id") or ""
            ), False
        try:
            result = TriageResult.model_validate(payload)
        except ValidationError:
            fallback = self._rules.classify(event["kind"])
            fallback.context_status = context_status
            return self._apply_verification_and_memory(
                fallback, raw, expected, calendar, event.get("device_id") or ""
            ), False
        result = self._apply_guardrails(result)
        result.context_status = context_status
        if not self._sanity(result, expected, raw):
            result = self._demote(result, event["kind"])
            result.context_status = context_status
        result = self._apply_verification_and_memory(
            result, raw, expected, calendar, event.get("device_id") or ""
        )
        return self._apply_quiet_hours(result, event["occurred_at"]), True

    def _apply_verification_and_memory(self, result, raw, expected, calendar, device_id):
        """Gatekeeper verification + same-as-last-time memory, on any path."""
        verification = verify_claim(raw, expected, calendar)
        result.verification_status = verification["verification_status"]
        result.risk_level = verification["risk_level"]
        result.claimed_identity = verification["claimed_identity"]
        result.challenge_question_en = verification["challenge_question_en"]
        result.challenge_question_vi = verification["challenge_question_vi"]
        if verification["verification_status"] in {"unverified", "contradiction"}:
            claim_caption = CLAIM_CAPTIONS.get(verification["claimed_identity"])
            if claim_caption:
                result.caption_en = claim_caption["en"]
                result.caption_vi = claim_caption["vi"]
        elif verification["verification_status"] == "verified":
            claim_caption = CLAIM_VERIFIED.get(verification["claimed_identity"])
            if claim_caption:
                result.caption_en = claim_caption["en"]
                result.caption_vi = claim_caption["vi"]
        claim = verification["claimed_identity"]
        if claim in {"police", "utility", "government"}:
            if verification["verification_status"] == "verified":
                result.suggested_replies = ["coming", "not_now"]
            else:
                result.suggested_replies = ["not_now"]
        elif claim in {"pharmacy", "package"}:
            result.suggested_replies = ["leave_at_door", "coming", "not_now"]
        elif claim == "family":
            result.suggested_replies = ["coming", "not_now", "waiting_for_parent"]
        last_reply = getattr(self._db, "last_reply_for_device", None)
        if last_reply is not None and device_id:
            try:
                previous = last_reply(device_id)
            except Exception:
                previous = None
            if previous and previous.get("category") == result.category.value:
                action = previous.get("action") or ""
                if action in REPLY_ACTIONS:
                    category = result.category.value
                    category_en = MEMORY_CATEGORY_LABELS.get(category, {}).get("en", category)
                    category_vi = MEMORY_CATEGORY_LABELS.get(category, {}).get("vi", category)
                    action_en = MEMORY_ACTION_LABELS.get(action, {}).get("en", action)
                    action_vi = MEMORY_ACTION_LABELS.get(action, {}).get("vi", action)
                    result.memory_action = action
                    result.memory_basis_en = MEMORY_BASIS_TEMPLATES["en"].format(
                        category=category_en, action=action_en
                    )
                    result.memory_basis_vi = MEMORY_BASIS_TEMPLATES["vi"].format(
                        category=category_vi, action=action_vi
                    )
        return result

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
            evidence.startswith(("expected_context", "user_label", "calendar", "visitor_statement"))
            for evidence in result.evidence
        )
        tags, label_hint = extract_payload_hints(raw)
        payload_grounded = bool(tags or label_hint or extract_visitor_statement(raw))
        if not (evidence_grounded or payload_grounded):
            return False
        return result.confidence >= 0.6 or bool(expected)

    @staticmethod
    def parse_payload(payload: dict) -> TriageResult:
        return TriageResult.model_validate(payload)