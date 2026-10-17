"""Measure Tier-1 and enrichment latency over N simulated events.

Default: in-process measurement with a temporary DB and the stub LLM.
With --base-url: replay against a running server (e.g. a deployed demo) and read
that server's own /api/metrics histograms instead.

Usage: python scripts/measure_latency.py [--count 100] [--json]
       python scripts/measure_latency.py --base-url https://demo.example.com [--token API_TOKEN]

Synthetic replay, not production telemetry.
"""

import argparse
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = (
    "doorbell_unknown",
    "doorbell_med",
    "doorbell_package_window",
    "doorbell_family",
    "motion_only",
    "motion_night",
)

TIMERS = ("tier1_ms", "context_ms", "enrich_ms", "webhook_to_sse_ms")


def measure_local(count: int) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APP_ENV"] = "development"
        os.environ["MOCK_MODE"] = "true"
        os.environ["API_AUTH_DISABLED"] = "true"
        os.environ["LLM_PROVIDER"] = "stub"
        os.environ["DB_URL"] = f"sqlite:///{Path(tmp) / 'latency.db'}"
        os.environ["RATE_LIMIT_PER_MINUTE"] = str(max(count * 2, 60))

        from fastapi.testclient import TestClient

        from backend.main import app

        with TestClient(app) as client:
            for index in range(count):
                response = client.post(f"/api/simulate?fixture={FIXTURES[index % len(FIXTURES)]}")
                response.raise_for_status()
            deadline = time.time() + 60
            while time.time() < deadline:
                timers = client.get("/api/metrics").json()["timers"]
                if timers.get("enrich_ms", {}).get("count", 0) >= count:
                    break
                time.sleep(0.1)
            snapshot = client.get("/api/metrics").json()
    timers = snapshot["timers"]
    return {
        "source": "local measurement (TestClient, stub LLM); not production telemetry",
        "count": count,
        "timers": {name: timers.get(name, {}) for name in TIMERS},
    }


def _fetch(url: str, token: str, method: str = "GET"):
    request = urllib.request.Request(url, data=b"" if method == "POST" else None, method=method)
    if token:
        request.add_header("authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def measure_remote(base_url: str, token: str, count: int) -> dict:
    base_url = base_url.rstrip("/")
    for index in range(count):
        _fetch(f"{base_url}/api/simulate?fixture={FIXTURES[index % len(FIXTURES)]}", token, method="POST")
    deadline = time.time() + 120
    snapshot = None
    while time.time() < deadline:
        snapshot = _fetch(f"{base_url}/api/metrics", token)
        if snapshot["timers"].get("enrich_ms", {}).get("count", 0) >= count:
            break
        time.sleep(0.25)
    timers = (snapshot or {}).get("timers", {})
    return {
        "source": (
            f"remote replay against {base_url} (server /api/metrics histograms); "
            "synthetic events, not production telemetry"
        ),
        "count": count,
        "timers": {name: timers.get(name, {}) for name in TIMERS},
    }


def render(report: dict) -> str:
    lines = [
        f"{report['source']} - {report['count']} simulated events",
        "",
        f"{'timer':<20}{'count':>7}{'p50 ms':>10}{'p95 ms':>10}{'max ms':>10}",
    ]
    for name in TIMERS:
        stats = report["timers"].get(name) or {}
        lines.append(
            f"{name:<20}{stats.get('count', 0):>7}{stats.get('p50', 0.0):>10}{stats.get('p95', 0.0):>10}{stats.get('max', 0.0):>10}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--base-url", default="", help="measure a running server instead of this machine")
    parser.add_argument("--token", default="", help="API bearer token for --base-url targets")
    args = parser.parse_args()
    if args.base_url:
        try:
            report = measure_remote(args.base_url, args.token, args.count)
        except urllib.error.HTTPError as exc:
            print(f"measurement target answered HTTP {exc.code}: {exc.reason}", file=sys.stderr)
            return 1
        except OSError as exc:
            print(f"cannot reach measurement target: {exc}", file=sys.stderr)
            return 1
    else:
        report = measure_local(args.count)
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
