import asyncio
import json

from .policy import policy_ref
from .util import iso_in, seconds_until


class EscalationManager:
    def __init__(self, db, broker, notifier):
        self._db = db
        self._broker = broker
        self._notifier = notifier
        self._tasks: dict[int, asyncio.Task] = {}

    def schedule(self, event_id: int, triage: dict) -> bool:
        policy = self._db.get_escalation_policy()
        if not policy["enabled"]:
            return False
        if (triage.get("urgency") or 0) < policy["min_urgency"]:
            return False
        contacts = self._db.list_escalation_contacts(enabled_only=True)
        if not contacts:
            return False
        timeout = policy["timeout_seconds"]
        self._db.upsert_pending_escalation(event_id, iso_in(timeout), timeout)
        self._cancel_existing(event_id)
        self._tasks[event_id] = asyncio.create_task(self._run(event_id, timeout, timeout))
        self._publish_armed(event_id, timeout, contacts)
        return True

    def _publish_armed(self, event_id: int, timeout: int, contacts: list[dict]):
        self._broker.publish(
            {
                "type": "escalation_armed",
                "event_id": event_id,
                "timeout_seconds": timeout,
                "contacts": [contact["label"] for contact in contacts],
            }
        )

    async def recover(self) -> int:
        pending = self._db.list_pending_escalations()
        contacts = self._db.list_escalation_contacts(enabled_only=True)
        for row in pending:
            event_id = row["event_id"]
            delay = max(0.0, seconds_until(row["fire_at"]))
            self._cancel_existing(event_id)
            self._tasks[event_id] = asyncio.create_task(
                self._run(event_id, delay, row["timeout_seconds"])
            )
            if contacts:
                self._publish_armed(event_id, row["timeout_seconds"], contacts)
        return len(pending)

    async def _run(self, event_id: int, delay: float, timeout_seconds: int):
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        self._tasks.pop(event_id, None)
        if not self._db.claim_pending_escalation(event_id):
            return
        if self._db.labels_for_event(event_id):
            return
        contacts = self._db.list_escalation_contacts(enabled_only=True)
        if not contacts:
            return
        event = self._db.get_event(event_id) or {}
        try:
            triage = json.loads(event.get("triage_json") or "{}")
        except (TypeError, ValueError):
            triage = {}
        caption = triage.get("caption_en") or "Someone is at the door"
        message = (
            "AccessBell: no response to a high-urgency door alert"
            f" (event {event_id}, policy {policy_ref()['short']}). Caption: {caption}"
        )
        for contact in contacts:
            result = self._notifier.escalate(contact["recipient"], message)
            status = "queued" if result.get("status") != "failed" else "failed"
            self._db.log_escalation(event_id, contact["id"], contact["recipient"], message, status)
        self._broker.publish(
            {
                "type": "escalation_sent",
                "event_id": event_id,
                "contacts": [c["label"] for c in contacts],
                "timeout_seconds": timeout_seconds,
            }
        )

    def acknowledge(self, event_id: int, source: str) -> bool:
        task = self._tasks.pop(event_id, None)
        if task is not None and not task.done():
            task.cancel()
        if not self._db.claim_pending_escalation(event_id):
            return False
        self._db.log_escalation(
            event_id,
            None,
            "audit",
            f"{source} responded within window - escalation stopped",
            "stopped",
        )
        return True

    def _cancel_existing(self, event_id: int):
        task = self._tasks.pop(event_id, None)
        if task and not task.done():
            task.cancel()

    def shutdown(self):
        for task in self._tasks.values():
            task.cancel()
        self._tasks.clear()