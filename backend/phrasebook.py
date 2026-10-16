"""Fixed-prompt EN<->VI phrasebook for door talk.

Exact-match only: this is NOT free-text translation. Any text that does not
exactly match one of the fixed prompts (case/whitespace/punctuation-insensitive)
returns None, and the caller must say translation is not available — never
present a phrasebook hit as a general translation.
"""

import re

from .captions import PHRASEBOOK


def normalize(text: str) -> str:
    """Lowercase, collapse whitespace, strip trailing punctuation."""
    cleaned = re.sub(r"\s+", " ", (text or "").strip().lower())
    return cleaned.rstrip(".!?").strip()


def pairs() -> list[dict]:
    """Fixed prompts as [{"en", "vi"}] for the web UI."""
    return [{"en": en, "vi": vi} for en, vi in PHRASEBOOK]


def lookup(text: str) -> dict | None:
    """Return {"text": translated, "lang": target} for an exact fixed-prompt match.

    Returns None when the text is not one of the fixed prompts.
    """
    target = normalize(text)
    if not target:
        return None
    for en, vi in PHRASEBOOK:
        if normalize(en) == target:
            return {"text": vi, "lang": "vi"}
        if normalize(vi) == target:
            return {"text": en, "lang": "en"}
    return None
