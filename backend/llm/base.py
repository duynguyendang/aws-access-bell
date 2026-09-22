from typing import Protocol


class TriageLLM(Protocol):
    name: str

    def triage(
        self,
        *,
        kind: str,
        device_id: str,
        occurred_at: str,
        raw: dict,
        expected: list[dict],
        labels: list[dict],
        calendar: list[dict],
    ) -> dict:
        ...