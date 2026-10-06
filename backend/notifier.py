import logging

logger = logging.getLogger("accessbell")


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
        provider = getattr(self._settings, "notifier_provider", "demo")
        if provider == "sns":
            try:
                import boto3

                region = getattr(self._settings, "aws_region", "us-east-1")
                client = boto3.client("sns", region_name=region)
                topic_arn = getattr(self._settings, "sns_topic_arn", None)
                if topic_arn and not recipient.startswith("+"):
                    res = client.publish(TopicArn=topic_arn, Message=message)
                else:
                    res = client.publish(PhoneNumber=recipient, Message=message)
                return {"channel": "sms", "status": "sent", "provider": "sns", "message_id": res.get("MessageId")}
            except Exception as exc:
                logger.warning("SNS publish failed: %s", exc)
                return {"channel": "sms", "status": "failed", "provider": "sns", "reason": str(exc), "error": str(exc)}
        return {"channel": "sms", "status": "skipped", "reason": "sms_not_configured_in_mvp"}

    def escalate(self, recipient: str, message: str) -> dict:
        provider = getattr(self._settings, "notifier_provider", "demo")
        if provider == "sns":
            sms_res = self.sms(recipient, message)
            return {
                "channel": "escalation",
                "status": sms_res["status"],
                "transport": "sns",
                "to": recipient,
                "reason": sms_res.get("reason", ""),
            }
        if provider == "ses":
            sender = getattr(self._settings, "ses_sender_email", None)
            if not sender:
                return {"channel": "escalation", "status": "failed", "reason": "ses_sender_email_not_configured"}
            try:
                import boto3

                region = getattr(self._settings, "aws_region", "us-east-1")
                client = boto3.client("ses", region_name=region)
                res = client.send_email(
                    Source=sender,
                    Destination={"ToAddresses": [recipient]},
                    Message={
                        "Subject": {"Data": "AccessBell Escalation Alert"},
                        "Body": {"Text": {"Data": message}},
                    },
                )
                return {
                    "channel": "escalation",
                    "status": "sent",
                    "transport": "ses",
                    "to": recipient,
                    "message_id": res.get("MessageId"),
                }
            except Exception as exc:
                logger.warning("SES send failed: %s", exc)
                return {"channel": "escalation", "status": "failed", "transport": "ses", "reason": str(exc), "error": str(exc)}
        return {"channel": "escalation", "status": "queued", "transport": "demo_mode", "to": recipient}