import re

from ..captions import stub_captions
from ..webhook import extract_payload_hints, extract_visitor_statement


def _hit(text: str, keys) -> bool:
    return any(re.search(rf"\b{re.escape(k)}\b", text) for k in keys)


def _statement_evidence(statement: str, keys, base: list[str]) -> list[str]:
    if statement and _hit(statement, keys):
        return base + ["visitor_statement"]
    return base


class StubLLM:
    name = "stub"

    def triage(self, *, kind, device_id, occurred_at, raw, expected, labels=None, calendar=None):
        tags, hint = extract_payload_hints(raw)
        statement = extract_visitor_statement(raw)
        statement_text = statement.lower().replace("_", " ")
        tags = [tag.lower() for tag in tags]
        hint = hint.lower()
        text = " ".join(tags + [hint, statement]).replace("_", " ")

        for item in calendar or []:
            label = str(item.get("title") or item.get("label") or "").lower().replace("_", " ")
            if _hit(label, ("pharmacy", "medicine", "med", "doctor", "drug")):
                return self._result("MED_DELIVERY", 8, 0.8, ["doorbell", "calendar:med"])
            if _hit(label, ("package", "delivery", "ship", "amazon")):
                return self._result("PACKAGE_DELIVERY", 6, 0.78, ["doorbell", "calendar:package"])
            if _hit(label, ("family", "guest", "visit", "relative")):
                return self._result("FAMILY_VISITOR", 3, 0.78, ["doorbell", "calendar:family"])

        for window in expected:
            label = str(window.get("label") or "").lower().replace("_", " ")
            if _hit(label, ("pharmacy", "medicine", "med", "doctor", "drug")):
                return self._result("MED_DELIVERY", 8, 0.85, ["doorbell", "expected_context:pharmacy"])
            if _hit(label, ("package", "delivery", "ship", "amazon")):
                return self._result("PACKAGE_DELIVERY", 6, 0.8, ["doorbell", "expected_context:package"])
            if _hit(label, ("family", "guest", "visit", "relative")):
                return self._result("FAMILY_VISITOR", 3, 0.8, ["doorbell", "expected_context:family"])

        if _hit(text, ("pharmacy", "medicine", "med", "doctor", "drug")):
            return self._result(
                "MED_DELIVERY",
                8,
                0.78,
                _statement_evidence(statement_text, ("pharmacy", "medicine", "med", "doctor", "drug"), ["doorbell"]),
            )
        if _hit(text, ("package", "delivery", "ship", "courier")):
            return self._result(
                "PACKAGE_DELIVERY",
                6,
                0.72,
                _statement_evidence(statement_text, ("package", "delivery", "ship", "courier"), ["doorbell"]),
            )
        if _hit(text, ("family", "guest", "visit", "relative")):
            return self._result(
                "FAMILY_VISITOR",
                3,
                0.72,
                _statement_evidence(statement_text, ("family", "guest", "visit", "relative"), ["doorbell"]),
            )

        if "motion" in str(kind).lower():
            urgency = 6 if "night" in tags else 5
            return self._result("MOTION_ANOMALY", urgency, 0.65, ["motion"])
        return self._result("UNKNOWN_VISITOR", 4, 0.7, ["doorbell"])

    @staticmethod
    def _result(category, urgency, confidence, evidence):
        captions = stub_captions(category)
        return {
            "category": category,
            "urgency": urgency,
            "confidence": confidence,
            "evidence": evidence,
            "caption_en": captions["en"],
            "caption_vi": captions["vi"],
            "suggested_replies": ["leave_at_door", "coming", "not_now"],
            "do_not_invent": True,
        }