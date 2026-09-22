import pytest

from backend.captions import (
    BRIEF,
    CHILD,
    GENERIC,
    LANGUAGES,
    MAX_CAPTION_LENGTH,
    QUIET,
    STUB,
    TIER1,
    UI,
    is_short_enough,
    is_tts_safe,
    render,
    ui_strings,
    why_text,
)
from backend.triage import Category


def _all_caption_strings():
    for group in (GENERIC, STUB, QUIET):
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
            formatted = raw.format(value=7, ms=12, seconds=90, contact="Lan", label="Leave package")
            assert is_tts_safe(formatted)
            assert is_short_enough(formatted)
    assert ui_strings("vi")["stop_escalation"] == UI["vi"]["stop_escalation"]
    assert ui_strings("unknown") == UI["en"]


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


def test_render_handles_singular_and_plural():
    assert render(BRIEF["en"]["med"], 1) == "You had 1 medicine-related visit."
    assert render(BRIEF["en"]["med"], 2) == "You had 2 medicine-related visits."