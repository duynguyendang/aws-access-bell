class Notifier:
    def __init__(self, settings):
        self._settings = settings

    def announce(self, event: dict, triage: dict) -> dict:
        if not self._settings.announce_enabled:
            return {"channel": "announce", "status": "skipped", "reason": "announce_disabled"}
        return {
            "channel": "announce",
            "status": "ok",
            "text": (triage or {}).get("caption_en", "Someone is at the door"),
        }

    def sms(self, recipient: str, message: str) -> dict:
        return {"channel": "sms", "status": "skipped", "reason": "sms_not_configured_in_mvp"}

    def escalate(self, recipient: str, message: str) -> dict:
        return {"channel": "escalation", "status": "queued", "transport": "demo_mode", "to": recipient}