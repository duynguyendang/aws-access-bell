import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_URL = "http://localhost:8000/webhooks/ring"
FIXTURES_DIR = Path(__file__).resolve().parents[1] / "data" / "mock_events"


def compute_signature(payload_bytes: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def post_webhook(url: str, payload_bytes: bytes, secret: str = "") -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-Signature"] = compute_signature(payload_bytes, secret)
    req = urllib.request.Request(url, data=payload_bytes, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return resp.status, data
    except urllib.error.HTTPError as exc:
        try:
            data = json.loads(exc.read().decode("utf-8"))
        except Exception:
            data = {"detail": str(exc)}
        return exc.code, data


def replay_file(file_path: Path, url: str, secret: str = "") -> tuple[int, dict]:
    payload_bytes = file_path.read_bytes()
    return post_webhook(url, payload_bytes, secret)


def main():
    parser = argparse.ArgumentParser(description="Replay Ring webhook payloads to AccessBell")
    parser.add_argument("--url", default=os.getenv("RING_WEBHOOK_URL", DEFAULT_URL), help="Webhook target URL")
    parser.add_argument("--secret", default=os.getenv("RING_WEBHOOK_SECRET", ""), help="Webhook HMAC secret")
    parser.add_argument("--fixture", help="Name or path of fixture to replay (omit to replay all)")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay in seconds between events")
    args = parser.parse_args()

    if args.fixture:
        path = Path(args.fixture)
        if not path.exists():
            path = FIXTURES_DIR / f"{args.fixture}.json"
        if not path.exists():
            sys.exit(f"Fixture not found: {args.fixture}")
        targets = [path]
    else:
        targets = sorted(FIXTURES_DIR.glob("*.json"))
        if not targets:
            sys.exit("No fixtures found in data/mock_events")

    for path in targets:
        name = path.stem
        status, resp = replay_file(path, args.url, args.secret)
        print(f"[{status}] {name} -> {resp}")
        if len(targets) > 1 and args.delay > 0:
            time.sleep(args.delay)


if __name__ == "__main__":
    main()
