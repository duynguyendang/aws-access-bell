import re

LANGUAGES = ("en", "vi")
MAX_CAPTION_LENGTH = 120

_TTS_UNSAFE_CHARS = set("#*_`<>{}[]|~^\\")
_EMOJI = re.compile("[\U0001f000-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff]")

GENERIC = {
    "UNKNOWN_VISITOR": {"en": "Someone is at the door", "vi": "Có người ở cửa"},
    "MOTION_ANOMALY": {"en": "Motion detected at the door", "vi": "Có chuyển động ở cửa"},
}

TIER1 = {
    "ding": {"category": "UNKNOWN_VISITOR", **GENERIC["UNKNOWN_VISITOR"]},
    "motion": {"category": "MOTION_ANOMALY", **GENERIC["MOTION_ANOMALY"]},
    "button_press": {"category": "UNKNOWN_VISITOR", **GENERIC["UNKNOWN_VISITOR"]},
    "motion_detected": {"category": "MOTION_ANOMALY", **GENERIC["MOTION_ANOMALY"]},
}

STUB = {
    "MED_DELIVERY": {
        "en": "Possible prescription or pharmacy delivery at the door",
        "vi": "Có thể là thuốc hoặc đơn hàng từ hiệu thuốc ở cửa",
    },
    "PACKAGE_DELIVERY": {
        "en": "Possible package delivery at the door",
        "vi": "Có thể có người giao hàng ở cửa",
    },
    "FAMILY_VISITOR": {
        "en": "Possible family or expected visitor at the door",
        "vi": "Có thể có người thân hoặc khách quen ở cửa",
    },
    **GENERIC,
}

BRIEF = {
    "en": {
        "med": "You had {n} medicine-related visit{s}.",
        "package": "You had {n} package delivery visit{s}.",
        "family": "You had {n} expected family/visitor call{s}.",
        "urgent": "Check the alert list for high-urgency visits.",
        "motion": "There were {n} motion detections.",
        "none": "No door events today.",
        "total": "{n} door event(s) total.",
    },
    "vi": {
        "med": "Hôm nay có {n} lượt liên quan đến thuốc.",
        "package": "Hôm nay có {n} lượt giao hàng.",
        "family": "Hôm nay có {n} lượt khách quen.",
        "urgent": "Vui lòng kiểm tra cảnh báo mức khẩn cấp cao.",
        "motion": "Có {n} lượt phát hiện chuyển động.",
        "none": "Hôm nay không có sự kiện cửa nào.",
        "total": "Tổng {n} sự kiện cửa.",
    },
}


CHILD = {
    "MED_DELIVERY": {
        "en": "Someone is bringing medicine to the door. You can wait for a grown-up.",
        "vi": "Có người mang thuốc đến cửa. Con có thể đợi người lớn.",
    },
    "PACKAGE_DELIVERY": {
        "en": "A delivery is at the door. You can wait for a parent.",
        "vi": "Có người giao hàng ở cửa. Con có thể đợi bố mẹ.",
    },
    "FAMILY_VISITOR": {
        "en": "A visitor is at the door. You can wait for a parent.",
        "vi": "Có khách ở cửa. Con có thể đợi bố mẹ.",
    },
    "UNKNOWN_VISITOR": {
        "en": "Someone is at the door. You can wait for a parent.",
        "vi": "Có người ở cửa. Con có thể đợi bố mẹ.",
    },
    "MOTION_ANOMALY": {
        "en": "There is movement at the door. You can wait for a parent.",
        "vi": "Có chuyển động ở cửa. Con có thể đợi bố mẹ.",
    },
}

GROUNDING = {
    "en": {
        "grounded": "Why: {evidence}.",
        "expected_context": "Why: matches your expected {label} window.",
        "calendar": "Why: matches your calendar ({label}).",
        "demoted": "Why generic: no expected window, label, or payload signal yet.",
        "generic": "Why generic: no specific match in the event.",
        "context_timeout": "Why generic: calendar context was slow, so only local signals were used.",
    },
    "vi": {
        "grounded": "Lý do: {evidence}.",
        "expected_context": "Lý do: khớp khung giờ bạn đã hẹn {label}.",
        "calendar": "Lý do: khớp lịch của bạn ({label}).",
        "demoted": "Vì sao chung chung: chưa có khung giờ hẹn, nhãn, hoặc tín hiệu nào.",
        "generic": "Vì sao chung chung: sự kiện không có dấu hiệu cụ thể.",
        "context_timeout": "Vì sao chung chung: ngữ cảnh lịch chậm nên chỉ dùng tín hiệu cục bộ.",
    },
}

QUIET = {
    "MOTION_ANOMALY": {
        "en": "Quiet hours: motion at the door",
        "vi": "Giờ yên tĩnh: có chuyển động ở cửa",
    },
}

UI = {
    "en": {
        "app_title": "AccessBell door alerts",
        "status_live": "Live",
        "status_connecting": "Connecting",
        "status_disconnected": "Disconnected",
        "recent_alerts": "Recent alerts",
        "urgency": "urgency {value}",
        "confidence": "confidence {value}",
        "evidence": "Evidence",
        "why": "Why",
        "grounded": "Grounded",
        "generic": "Generic",
        "demoted": "Generic, no evidence yet",
        "context_timeout": "Calendar was slow",
        "latency": "Tier 1 in {ms} ms",
        "child_mode_on": "Child mode on",
        "child_mode_off": "Child mode off",
        "voice_on": "Voice on",
        "voice_off": "Voice off",
        "language": "Language",
        "reply_leave": "Leave package",
        "reply_coming": "I am coming",
        "reply_not_now": "Not now",
        "reply_waiting": "Waiting for parent",
        "reply_sent": "Reply sent: {label}",
        "reply_failed": "Reply failed",
        "escalation_waiting": "No answer in {seconds} seconds, then contact {contact}",
        "escalation_sent": "No answer: contacted {contact}",
        "escalation_stopped": "Escalation stopped",
        "stop_escalation": "Stop escalation",
        "door_calendar": "Door calendar",
        "window_label": "Expected visitor or delivery",
        "window_start": "From",
        "window_end": "To",
        "add_window": "Add window",
        "clear": "Clear",
        "no_windows": "No expected windows",
        "share_title": "Share brief",
        "recipient": "Send to",
        "preview": "Preview",
        "share_now": "Share brief",
        "consent_label": "I consent to share this brief",
        "revoke": "Revoke",
        "no_shares": "No shares yet",
        "simulate": "Simulate doorbell",
        "no_events": "No alerts yet",
    },
    "vi": {
        "app_title": "Cảnh báo cửa AccessBell",
        "status_live": "Đang trực tiếp",
        "status_connecting": "Đang kết nối",
        "status_disconnected": "Mất kết nối",
        "recent_alerts": "Cảnh báo gần đây",
        "urgency": "mức khẩn {value}",
        "confidence": "độ tin cậy {value}",
        "evidence": "Bằng chứng",
        "why": "Vì sao",
        "grounded": "Có căn cứ",
        "generic": "Chung chung",
        "demoted": "Chung chung, chưa có bằng chứng",
        "context_timeout": "Lịch phản hồi chậm",
        "latency": "Tầng 1 trong {ms} mili giây",
        "child_mode_on": "Đang bật chế độ trẻ em",
        "child_mode_off": "Đang tắt chế độ trẻ em",
        "voice_on": "Đã bật giọng nói",
        "voice_off": "Đã tắt giọng nói",
        "language": "Ngôn ngữ",
        "reply_leave": "Để hàng ở cửa",
        "reply_coming": "Tôi ra ngay",
        "reply_not_now": "Để sau",
        "reply_waiting": "Đợi bố mẹ",
        "reply_sent": "Đã trả lời: {label}",
        "reply_failed": "Gửi trả lời thất bại",
        "escalation_waiting": "Không trả lời trong {seconds} giây sẽ báo {contact}",
        "escalation_sent": "Không ai trả lời: đã báo {contact}",
        "escalation_stopped": "Đã dừng báo động",
        "stop_escalation": "Dừng báo động",
        "door_calendar": "Lịch cửa",
        "window_label": "Khách hoặc đơn hàng dự kiến",
        "window_start": "Từ",
        "window_end": "Đến",
        "add_window": "Thêm khung giờ",
        "clear": "Xóa",
        "no_windows": "Chưa có khung giờ dự kiến",
        "share_title": "Chia sẻ bản tin",
        "recipient": "Gửi đến",
        "preview": "Xem trước",
        "share_now": "Chia sẻ bản tin",
        "consent_label": "Tôi đồng ý chia sẻ bản tin này",
        "revoke": "Thu hồi",
        "no_shares": "Chưa có chia sẻ nào",
        "simulate": "Mô phỏng chuông cửa",
        "no_events": "Chưa có cảnh báo",
    },
}


def ui_strings(language: str) -> dict:
    return dict(UI.get(language, UI["en"]))


def is_tts_safe(text: str) -> bool:
    return not (set(text) & _TTS_UNSAFE_CHARS) and not _EMOJI.search(text)


def is_short_enough(text: str) -> bool:
    return len(text) <= MAX_CAPTION_LENGTH


def generic_captions(category_value: str) -> dict | None:
    return GENERIC.get(category_value)


def stub_captions(category_value: str) -> dict | None:
    return STUB.get(category_value)


def child_captions(category_value: str) -> dict | None:
    return CHILD.get(category_value)


def quiet_captions(category_value: str) -> dict | None:
    return QUIET.get(category_value)


def why_text(
    *,
    grounding: str,
    evidence: list[str] | None = None,
    expected_label: str = "",
    calendar_label: str = "",
    context_status: str = "disabled",
    language: str = "en",
) -> str:
    templates = GROUNDING.get(language, GROUNDING["en"])
    evidence = evidence or []
    if context_status == "timeout" and grounding in {"generic", "demoted_insufficient_evidence"}:
        return templates["context_timeout"]
    if grounding == "demoted_insufficient_evidence":
        return templates["demoted"]
    if expected_label:
        return templates["expected_context"].format(label=expected_label)
    if calendar_label:
        return templates["calendar"].format(label=calendar_label)
    if grounding == "grounded":
        first = next((item for item in evidence if item), "the event")
        if first.startswith("calendar:"):
            return templates["calendar"].format(label=first.split(":", 1)[1] or "schedule")
        if first.startswith("expected_context:"):
            return templates["expected_context"].format(label=first.split(":", 1)[1] or "window")
        return templates["grounded"].format(evidence=first.replace(":", " "))
    return templates["generic"]


def render(template: str, count: int) -> str:
    return template.format(n=count, s="" if count == 1 else "s")