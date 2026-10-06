from unittest.mock import MagicMock, patch

from backend.config import Settings
from backend.notifier import Notifier


def test_notifier_demo_mode():
    settings = Settings(notifier_provider="demo")
    notifier = Notifier(settings)

    sms_res = notifier.sms("+1234567890", "Test message")
    assert sms_res["status"] == "skipped"
    assert sms_res["channel"] == "sms"

    esc_res = notifier.escalate("+1234567890", "Escalation message")
    assert esc_res["status"] == "queued"
    assert esc_res["transport"] == "demo_mode"


def test_notifier_announce():
    settings = Settings(announce_enabled=True)
    notifier = Notifier(settings)
    ann = notifier.announce({}, {"caption_en": "Package delivered"})
    assert ann["status"] == "ok"
    assert ann["text"] == "Package delivered"

    disabled_settings = Settings(announce_enabled=False)
    notifier_disabled = Notifier(disabled_settings)
    ann_disabled = notifier_disabled.announce({}, {"caption_en": "Package delivered"})
    assert ann_disabled["status"] == "skipped"


def test_notifier_sns_phone():
    settings = Settings(notifier_provider="sns", aws_region="us-east-1")
    notifier = Notifier(settings)

    mock_client = MagicMock()
    mock_client.publish.return_value = {"MessageId": "msg-123"}
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    with patch.dict("sys.modules", {"boto3": mock_boto3}):
        res = notifier.sms("+15551234567", "Hello via SNS")
        assert res["status"] == "sent"
        assert res["message_id"] == "msg-123"
        mock_client.publish.assert_called_once_with(PhoneNumber="+15551234567", Message="Hello via SNS")

        esc = notifier.escalate("+15551234567", "Urgent escalation")
        assert esc["status"] == "sent"
        assert esc["transport"] == "sns"


def test_notifier_sns_topic():
    settings = Settings(
        notifier_provider="sns",
        aws_region="us-east-1",
        sns_topic_arn="arn:aws:sns:us-east-1:123456789012:accessbell-alerts",
    )
    notifier = Notifier(settings)

    mock_client = MagicMock()
    mock_client.publish.return_value = {"MessageId": "topic-msg-456"}
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    with patch.dict("sys.modules", {"boto3": mock_boto3}):
        res = notifier.sms("caregiver", "Alert for caregiver")
        assert res["status"] == "sent"
        assert res["message_id"] == "topic-msg-456"
        mock_client.publish.assert_called_once_with(
            TopicArn="arn:aws:sns:us-east-1:123456789012:accessbell-alerts",
            Message="Alert for caregiver",
        )


def test_notifier_ses():
    settings = Settings(
        notifier_provider="ses",
        aws_region="us-east-1",
        ses_sender_email="alerts@accessbell.example.com",
    )
    notifier = Notifier(settings)

    mock_client = MagicMock()
    mock_client.send_email.return_value = {"MessageId": "ses-msg-789"}
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    with patch.dict("sys.modules", {"boto3": mock_boto3}):
        esc = notifier.escalate("family@example.com", "Door alert notification")
        assert esc["status"] == "sent"
        assert esc["transport"] == "ses"
        assert esc["message_id"] == "ses-msg-789"
        mock_client.send_email.assert_called_once()


def test_notifier_ses_missing_sender():
    settings = Settings(notifier_provider="ses")
    notifier = Notifier(settings)

    esc = notifier.escalate("family@example.com", "Door alert notification")
    assert esc["status"] == "failed"
    assert "ses_sender_email_not_configured" in esc["reason"]
