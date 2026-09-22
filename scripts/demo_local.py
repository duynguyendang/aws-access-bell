"""Push demo fixtures through the running AccessBell API."""

import sys
import time
import urllib.request

BASE = "http://localhost:8080"
FIXTURES = [
    "doorbell_unknown",
    "doorbell_package_window",
    "doorbell_med",
    "doorbell_family",
    "motion_only",
    "motion_night",
]


def post(path):
    req = urllib.request.Request(BASE + path, data=b"", method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8")
        print(resp.status, path, body)
        return body


def main():
    fixtures = sys.argv[1:] or FIXTURES
    for fixture in fixtures:
        post(f"/api/simulate?fixture={fixture}")
        time.sleep(3)
    print("done")


if __name__ == "__main__":
    main()