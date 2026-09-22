import threading
from collections import deque


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    rank = max(0, min(len(values) - 1, int(round((pct / 100.0) * (len(values) - 1)))))
    return values[rank]


class Metrics:
    def __init__(self, maxlen: int = 512):
        self._maxlen = maxlen
        self._lock = threading.Lock()
        self._timers: dict[str, deque] = {}
        self._counters: dict[str, int] = {}

    def observe(self, name: str, value_ms: float):
        with self._lock:
            self._timers.setdefault(name, deque(maxlen=self._maxlen)).append(float(value_ms))

    def increment(self, name: str, amount: int = 1):
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + amount

    def snapshot(self) -> dict:
        with self._lock:
            timers = {}
            for name, samples in self._timers.items():
                ordered = sorted(samples)
                timers[name] = {
                    "count": len(ordered),
                    "p50": round(_percentile(ordered, 50), 1),
                    "p95": round(_percentile(ordered, 95), 1),
                    "max": round(ordered[-1], 1) if ordered else 0.0,
                }
            return {"timers": timers, "counters": dict(self._counters)}


metrics = Metrics()