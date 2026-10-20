import pytest

from backend.captions import (
    BRIEF,
    CHALLENGE,
    CHALLENGE_BY_CLAIM,
    CHILD,
    CLAIM,
    CLAIM_VERIFIED,
    ESCALATION,
    GENERIC,
    LANGUAGES,
    MAX_CAPTION_LENGTH,
    MEMORY_ACTION,
    MEMORY_BASIS,
    MEMORY_CATEGORY,
    NONE_LABEL,
    PHRASEBOOK,
    QUIET,
    STUB,
    TIER1,
    UI,
    VERIFICATION_LABEL,
    is_short_enough,
    is_tts_safe,
    render,
    ui_strings,
    why_text,
)
from backend.triage import Category


def _all_caption_strings():
    for group in (GENERIC, STUB, QUIET, CLAIM, CLAIM_VERIFIED):
        for category, captions in group.items():
            for language, text in captions.items():
                yield f"{category}/{language}", text
    for kind, entry in TIER1.items():
        for language in LANGUAGES:
            yield f"tier1:{kind}/{language}", entry[language]


def test_every_language_present_for_generic_captions():
    for category in ("UNKNOWN_VISITOR", "MOTION_ANOMALY"):
        for language in LANGUAGES:
            assert GENERIC[category][language].strip()


def test_every_category_has_a_caption():
    for category in Category:
        assert category.value in STUB


def test_tier1_kinds_map_to_known_categories():
    for entry in TIER1.values():
        assert entry["category"] in STUB


def test_tier1_covers_partner_api_event_types():
    assert TIER1["button_press"]["category"] == "UNKNOWN_VISITOR"
    assert TIER1["motion_detected"]["category"] == "MOTION_ANOMALY"


@pytest.mark.parametrize("label,text", list(_all_caption_strings()))
def test_vietnamese_captions_refer_to_the_door(label, text):
    if not label.endswith("/vi"):
        return
    assert " ở ca" not in text, f"{label} looks like a typo for 'cửa'"
    assert "sự kiện ca" not in text, f"{label} looks like a typo for 'cửa'"


@pytest.mark.parametrize("label,text", list(_all_caption_strings()))
def test_captions_are_tts_safe(label, text):
    assert is_tts_safe(text), f"{label} contains characters that TTS/screen readers handle badly"


@pytest.mark.parametrize("label,text", list(_all_caption_strings()))
def test_captions_are_short(label, text):
    assert is_short_enough(text), f"{label} exceeds {MAX_CAPTION_LENGTH} characters"


def test_brief_templates_cover_both_languages():
    for language in LANGUAGES:
        assert language in BRIEF
        for key in ("med", "package", "family", "urgent", "motion", "none", "total"):
            assert key in BRIEF[language]


@pytest.mark.parametrize("count", [1, 3])
def test_brief_render_is_tts_safe(count):
    for language in LANGUAGES:
        for key, template in BRIEF[language].items():
            if key == "urgent":
                continue
            assert is_tts_safe(render(template, count))
            assert is_short_enough(render(template, count))


def test_child_captions_cover_all_categories_and_languages():
    for category in Category:
        assert category.value in CHILD
        for language in LANGUAGES:
            text = CHILD[category.value][language]
            assert text.strip()
            assert is_tts_safe(text)
            assert is_short_enough(text)


def test_ui_strings_are_complete_and_safe():
    assert set(UI["en"]) == set(UI["vi"])
    for key in UI["en"]:
        for language in LANGUAGES:
            raw = UI[language][key]
            assert raw.strip()
            formatted = raw.format(
                value=7,
                ms=12,
                seconds=90,
                contact="Lan",
                label="Leave package",
                id=12,
                text="I am at the door",
            )
            assert is_tts_safe(formatted)
            assert is_short_enough(formatted)
    assert ui_strings("vi")["stop_escalation"] == UI["vi"]["stop_escalation"]
    assert ui_strings("unknown") == UI["en"]


def test_challenge_and_memory_strings_are_complete_and_safe():
    for language in LANGUAGES:
        challenge = CHALLENGE[language]
        assert challenge.strip()
        assert is_tts_safe(challenge)
        assert is_short_enough(challenge)
        for claim, text in CHALLENGE_BY_CLAIM.items():
            value = text[language]
            assert value.strip(), claim
            assert is_tts_safe(value), claim
            assert is_short_enough(value), claim
        for mapping in (MEMORY_CATEGORY, MEMORY_ACTION):
            for entry in mapping.values():
                text = entry[language]
                assert text.strip()
                assert is_tts_safe(text)
                assert is_short_enough(text)
        basis = MEMORY_BASIS[language].format(
            category=MEMORY_CATEGORY["MED_DELIVERY"][language],
            action=MEMORY_ACTION["leave_at_door"][language],
        )
        assert basis.strip()
        assert is_tts_safe(basis)
        assert is_short_enough(basis)
    for en, vi in PHRASEBOOK:
        assert en.strip() and vi.strip()
        assert is_tts_safe(en) and is_tts_safe(vi)
        assert is_short_enough(en) and is_short_enough(vi)


def test_why_text_explains_context_timeout():
    text = why_text(grounding="generic", context_status="timeout")
    assert "calendar" in text.lower()
    vi = why_text(grounding="generic", context_status="timeout", language="vi")
    assert vi.strip() and is_tts_safe(vi)


def test_why_text_is_safe_for_every_grounding_state():
    for language in LANGUAGES:
        for grounding in ("grounded", "generic", "demoted_insufficient_evidence"):
            text = why_text(grounding=grounding, evidence=["doorbell"], language=language)
            assert text.strip()
            assert is_tts_safe(text)
            assert is_short_enough(text)
    expected = why_text(grounding="grounded", evidence=["expected_context:pharmacy"])
    assert "pharmacy" in expected
    calendar = why_text(grounding="grounded", evidence=["calendar:Pharmacy delivery"])
    assert "Pharmacy delivery" in calendar
    verified = why_text(grounding="generic", verification_status="verified")
    assert "schedule" in verified
    verified_vi = why_text(grounding="generic", verification_status="verified", language="vi")
    assert is_tts_safe(verified_vi) and is_short_enough(verified_vi)
    unverified = why_text(grounding="generic", verification_status="unverified")
    assert "no window" in unverified
    unverified_vi = why_text(grounding="generic", verification_status="unverified", language="vi")
    assert is_tts_safe(unverified_vi) and is_short_enough(unverified_vi)
    contradiction = why_text(grounding="generic", verification_status="contradiction")
    assert "conflicts" in contradiction
    contradiction_vi = why_text(
        grounding="generic", verification_status="contradiction", language="vi"
    )
    assert is_tts_safe(contradiction_vi) and is_short_enough(contradiction_vi)


def test_render_handles_singular_and_plural():
    assert render(BRIEF["en"]["med"], 1) == "You had 1 medicine-related visit."
    assert render(BRIEF["en"]["med"], 2) == "You had 2 medicine-related visits."


def test_escalation_message_is_bilingual_and_tts_safe():
    for language in LANGUAGES:
        message = ESCALATION[language].format(
            event_id=7,
            policy="abc123",
            verification=VERIFICATION_LABEL["unverified"][language],
            claim="pharmacy",
            caption=CLAIM["pharmacy"][language],
        )
        assert message.strip()
        assert is_tts_safe(message)
        assert "pharmacy" in message
        assert CLAIM["pharmacy"][language] in message
    assert set(VERIFICATION_LABEL) == {"verified", "unverified", "contradiction", "no_claim"}
    for label in VERIFICATION_LABEL.values():
        for language in LANGUAGES:
            assert label[language].strip()
            assert is_tts_safe(label[language])
            assert is_short_enough(label[language])
    for language in LANGUAGES:
        assert NONE_LABEL[language].strip()
        assert is_tts_safe(NONE_LABEL[language])