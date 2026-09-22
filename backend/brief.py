import json
from collections import Counter
from datetime import date as _date

from .captions import BRIEF, render


def _buckets(rows):
    by_category = Counter()
    urgent = []
    for event in rows:
        try:
            triage = json.loads(event.get("triage_json") or "{}")
        except (TypeError, ValueError):
            triage = {}
        category = triage.get("category") or "UNKNOWN"
        if category:
            by_category[category] += 1
        if (triage.get("urgency") or 0) >= 7:
            urgent.append(triage.get("caption_en", ""))
    return by_category, urgent


def _bullets(by_category, urgent, language):
    templates = BRIEF.get(language, BRIEF["en"])
    lines = []
    if by_category["MED_DELIVERY"]:
        lines.append(render(templates["med"], by_category["MED_DELIVERY"]))
    if by_category["PACKAGE_DELIVERY"]:
        lines.append(render(templates["package"], by_category["PACKAGE_DELIVERY"]))
    if by_category["FAMILY_VISITOR"]:
        lines.append(render(templates["family"], by_category["FAMILY_VISITOR"]))
    if urgent:
        lines.append(templates["urgent"])
    if by_category["MOTION_ANOMALY"]:
        lines.append(render(templates["motion"], by_category["MOTION_ANOMALY"]))
    if not lines:
        lines.append(templates["none"])
    lines.append(render(templates["total"], sum(by_category.values())))
    return lines


def build_daily_summary(db, day: str | None = None, language: str = "en") -> dict:
    day = day or _date.today().isoformat()
    start = f"{day}T00:00:00Z"
    end = f"{day}T23:59:59Z"
    rows = db.list_events(since=start, until=end, limit=1000)
    by_category, urgent = _buckets(rows)
    return {
        "date": day,
        "language": language,
        "total": len(rows),
        "by_category": dict(by_category),
        "med_deliveries": by_category["MED_DELIVERY"],
        "package_deliveries": by_category["PACKAGE_DELIVERY"],
        "high_urgency": len(urgent),
        "bullets": _bullets(by_category, urgent, language),
    }