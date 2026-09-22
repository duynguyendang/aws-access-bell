import threading
import time
from datetime import datetime, timedelta, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_in(seconds: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def seconds_until(value: str) -> float:
    return (parse_iso(value) - datetime.now(timezone.utc)).total_seconds()


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def seconds_between(a: str, b: str) -> float:
    return abs((parse_iso(b) - parse_iso(a)).total_seconds())


def is_quiet_hours(value: str, start: str, end: str) -> bool:
    if not start or not end:
        return False
    try:
        hour = parse_iso(value).hour
        start_hour = int(str(start).split(":", 1)[0])
        end_hour = int(str(end).split(":", 1)[0])
    except (TypeError, ValueError, IndexError):
        return False
    if start_hour == end_hour:
        return False
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60, max_keys: int = 4096):
        self._limit = limit
        self._window = window_seconds
        self._max_keys = max_keys
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, now: float):
        if len(self._hits) <= self._max_keys:
            return
        self._hits = {
            key: recent
            for key, recent in self._hits.items()
            if any(now - t < self._window for t in recent)
        }

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            recent = [t for t in self._hits.get(key, []) if now - t < self._window]
            if len(recent) >= self._limit:
                self._hits[key] = recent
                return False
            recent.append(now)
            self._hits[key] = recent
            self._prune(now)
            return True