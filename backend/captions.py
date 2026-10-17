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
        "vi": "Có thể là đơn giao thuốc ở cửa",
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
        "med": "Hôm nay có {n} lượt giao thuốc.",
        "package": "Hôm nay có {n} lượt giao hàng.",
        "family": "Hôm nay có {n} lượt người thân ghé thăm.",
        "urgent": "Vui lòng kiểm tra cảnh báo mức khẩn cấp cao.",
        "motion": "Có {n} lượt phát hiện chuyển động.",
        "none": "Hôm nay không có sự kiện nào ở cửa.",
        "total": "Tổng cộng {n} sự kiện ở cửa.",
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
        "vi": "Có người thân hoặc khách ở cửa. Con có thể đợi bố mẹ.",
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
        "expected_context": "Lý do: khớp khung giờ dự kiến ({label}).",
        "calendar": "Lý do: khớp lịch của bạn ({label}).",
        "demoted": "Thông báo chung: chưa có khung giờ hẹn hoặc bằng chứng cụ thể.",
        "generic": "Thông báo chung: sự kiện không có dấu hiệu cụ thể.",
        "context_timeout": "Thông báo chung: phản hồi lịch bị trễ nên chỉ dùng tín hiệu cục bộ.",
    },
}

QUIET = {
    "MOTION_ANOMALY": {
        "en": "Quiet hours: motion at the door",
        "vi": "Giờ yên tĩnh: có chuyển động ở cửa",
    },
}

MEMORY_CATEGORY = {
    "MED_DELIVERY": {"en": "medicine delivery", "vi": "giao thuốc"},
    "PACKAGE_DELIVERY": {"en": "package delivery", "vi": "giao hàng"},
    "FAMILY_VISITOR": {"en": "family visit", "vi": "người thân"},
    "UNKNOWN_VISITOR": {"en": "unknown visitor", "vi": "khách lạ"},
    "MOTION_ANOMALY": {"en": "motion", "vi": "chuyển động"},
}

MEMORY_ACTION = {
    "leave_at_door": {"en": "Leave package", "vi": "Để gói hàng ở cửa"},
    "coming": {"en": "I am coming", "vi": "Tôi ra ngay"},
    "not_now": {"en": "Not now", "vi": "Lúc khác"},
    "waiting_for_parent": {"en": "Waiting for parent", "vi": "Đợi bố mẹ"},
}

CHALLENGE = {
    "en": "Ask for order number / ID and callback number. Do not open.",
    "vi": "Hỏi mã đơn hàng / giấy tờ và số gọi lại. Đừng mở cửa.",
}

MEMORY_BASIS = {
    "en": "Last time for {category} you chose: {action}.",
    "vi": "Lần trước với {category} bạn đã chọn: {action}.",
}

PHRASEBOOK = [
    ("Who are you?", "Bạn là ai?"),
    ("Who are you here to see?", "Bạn đến gặp ai?"),
    ("Do you have an appointment?", "Bạn có hẹn trước không?"),
    ("What is your order number?", "Mã đơn hàng của bạn là gì?"),
    ("Please wait a moment.", "Vui lòng đợi một chút."),
    ("Please leave it at the door.", "Vui lòng để ở cửa."),
]

UI = {
    "en": {
        "app_title": "AccessBell door alerts",
        "status_live": "Live",
        "status_connecting": "Connecting",
        "status_disconnected": "Disconnected",
        "advise_title": "Suggested reminders (read-only)",
        "recent_alerts": "Recent alerts",
        "export_log": "Download door log",
        "export_log_title": "AccessBell door log",
        "export_log_note": "Exported from this device's AccessBell database; in mock mode the events are fixture-derived.",
        "export_log_failed": "Door log export failed",
        "export_challenge": "Challenge",
        "export_policy": "Policy {value}",
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
        "bilingual_mode_on": "Bilingual EN+VI on",
        "bilingual_mode_off": "Bilingual EN+VI off",
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
        "demo_en": "Demo EN (Medicine)",
        "demo_vi": "Demo VI (Medicine)",
        "fixture_doorbell_med": "Medicine Delivery",
        "fixture_doorbell_package_window": "Package Delivery",
        "fixture_doorbell_family": "Family Visitor",
        "fixture_doorbell_unknown": "Unknown Visitor",
        "fixture_doorbell_police_claim": "Police Claim",
        "fixture_motion_only": "Motion",
        "fixture_motion_night": "Night Motion",
        "verification_verified": "Verified",
        "verification_unverified": "Unverified",
        "verification_contradiction": "Contradiction — check details",
        "verification_no_claim": "No claim",
        "risk_low": "Risk: low",
        "risk_medium": "Risk: medium",
        "risk_high": "Risk: high",
        "memory_use_same": "Use same reply",
        "talk_title": "Talk to visitor",
        "talk_speaker": "Speaker",
        "talk_speaker_visitor": "Visitor",
        "talk_speaker_resident": "Resident",
        "talk_placeholder": "Type what to say…",
        "talk_send": "Send",
        "talk_mic": "Mic",
        "talk_speak": "Speak",
        "talk_translate": "Translate (fixed prompts only)",
        "talk_no_translation": "No fixed-prompt translation for this text.",
        "talk_mic_unsupported": "Mic not supported in this browser — type instead.",
        "talk_sent": "Message sent",
    },
    "vi": {
        "app_title": "Cảnh báo cửa AccessBell",
        "status_live": "Trực tiếp",
        "status_connecting": "Đang kết nối",
        "status_disconnected": "Mất kết nối",
        "advise_title": "Gợi ý nhắc nhở (chỉ đọc)",
        "recent_alerts": "Cảnh báo gần đây",
        "export_log": "Tải nhật ký cửa",
        "export_log_title": "Nhật ký cửa AccessBell",
        "export_log_note": "Xuất từ cơ sở dữ liệu AccessBell trên thiết bị này; ở chế độ mô phỏng, sự kiện là dữ liệu mẫu.",
        "export_log_failed": "Xuất nhật ký cửa thất bại",
        "export_challenge": "Câu hỏi xác minh",
        "export_policy": "Chính sách {value}",
        "urgency": "Mức khẩn {value}",
        "confidence": "Độ tin cậy {value}",
        "evidence": "Bằng chứng",
        "why": "Lý do",
        "grounded": "Có căn cứ",
        "generic": "Chung",
        "demoted": "Chung, chưa có bằng chứng",
        "context_timeout": "Lịch phản hồi chậm",
        "latency": "Tầng 1: {ms} ms",
        "child_mode_on": "Chế độ trẻ em: Bật",
        "child_mode_off": "Chế độ trẻ em: Tắt",
        "voice_on": "Giọng nói: Bật",
        "voice_off": "Giọng nói: Tắt",
        "bilingual_mode_on": "Chế độ song ngữ EN+VI: Bật",
        "bilingual_mode_off": "Chế độ song ngữ EN+VI: Tắt",
        "language": "Ngôn ngữ",
        "reply_leave": "Để gói hàng ở cửa",
        "reply_coming": "Tôi ra ngay",
        "reply_not_now": "Lúc khác quay lại",
        "reply_waiting": "Đợi bố mẹ",
        "reply_sent": "Đã trả lời: {label}",
        "reply_failed": "Gửi trả lời thất bại",
        "escalation_waiting": "Không trả lời trong {seconds} giây sẽ báo {contact}",
        "escalation_sent": "Không ai trả lời: đã báo {contact}",
        "escalation_stopped": "Đã dừng chuyển tiếp",
        "stop_escalation": "Dừng chuyển tiếp",
        "door_calendar": "Lịch hẹn trước cửa",
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
        "demo_en": "Bản demo EN (Giao thuốc)",
        "demo_vi": "Bản demo VI (Giao thuốc)",
        "fixture_doorbell_med": "Giao thuốc",
        "fixture_doorbell_package_window": "Giao hàng",
        "fixture_doorbell_family": "Người thân",
        "fixture_doorbell_unknown": "Khách lạ",
        "fixture_doorbell_police_claim": "Người tự nhận công an",
        "fixture_motion_only": "Chuyển động",
        "fixture_motion_night": "Chuyển động đêm",
        "verification_verified": "Đã xác minh",
        "verification_unverified": "Chưa xác minh",
        "verification_contradiction": "Mâu thuẫn — kiểm tra lại",
        "verification_no_claim": "Không có tuyên bố",
        "risk_low": "Rủi ro: thấp",
        "risk_medium": "Rủi ro: trung bình",
        "risk_high": "Rủi ro: cao",
        "memory_use_same": "Dùng trả lời cũ",
        "talk_title": "Nói chuyện với khách",
        "talk_speaker": "Người nói",
        "talk_speaker_visitor": "Khách",
        "talk_speaker_resident": "Người nhà",
        "talk_placeholder": "Nhập câu muốn nói…",
        "talk_send": "Gửi",
        "talk_mic": "Mic",
        "talk_speak": "Đọc",
        "talk_translate": "Dịch (chỉ câu mẫu)",
        "talk_no_translation": "Câu này không có bản dịch mẫu.",
        "talk_mic_unsupported": "Trình duyệt không hỗ trợ mic — hãy gõ tay.",
        "talk_sent": "Đã gửi tin nhắn",
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