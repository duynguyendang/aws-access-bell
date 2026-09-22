"""Drive the AccessBell demo story against a running server.

    # terminal 1
    MOCK_MODE=true LLM_PROVIDER=stub .venv/bin/python -m uvicorn backend.main:app --port 8080
    # terminal 2
    .venv/bin/python scripts/demo_story.py --pace 3
    .venv/bin/python scripts/demo_story.py --calendar http://127.0.0.1:8085/mcp
    .venv/bin/python scripts/demo_story.py --url https://my-host --token "$API_TOKEN"

Start from a fresh database (DB_URL pointing at a new file) so the counters in the
proof beat match what is on screen. Narration lines are the ones used in the video.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from uuid import uuid4

PHARMACY_WINDOW = {
    "kind": "ding",
    "label": "pharmacy refill",
    "window_start": "2026-09-15T09:00:00Z",
    "window_end": "2026-09-15T10:30:00Z",
}

CALENDAR_EVENT = {
    "title": "Pharmacy pickup",
    "start": "2026-09-16T09:00:00Z",
    "end": "2026-09-16T10:30:00Z",
}

PACKAGE_WINDOW = {
    "kind": "ding",
    "label": "amazon package",
    "window_start": "2026-09-15T13:00:00Z",
    "window_end": "2026-09-15T16:00:00Z",
}

CALM_EVENT_TIME = "2026-09-16T09:45:00Z"
CALM_EVENT_MS = 1789551900000
OPEN_EVENT_TIME = "2026-09-15T20:00:00Z"
OPEN_EVENT_MS = 1789502400000


def safe_json(text):
    try:
        return json.loads(text or "{}")
    except ValueError:
        return {"raw": text}


def call(method, url, payload=None, token=""):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, safe_json(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, safe_json(exc.read().decode("utf-8", "replace"))
    except urllib.error.URLError as exc:
        print(f"    cannot reach {url}: {exc}", file=sys.stderr)
        raise SystemExit(2)


class Demo:
    def __init__(self, args):
        self.base = args.url.rstrip("/")
        self.token = args.token
        self.pace = max(args.pace, 0)
        self.date = args.date
        self.calendar_mode = bool(args.calendar)

    def bare_ring(self, when, milliseconds, prefix):
        webhook = {
            "meta": {"version": "1.1", "time": when, "request_id": f"{prefix}-{uuid4().hex[:8]}",
                     "account_id": "ava1.ring.account.demo"},
            "data": {"id": f"front_door_button_press_{milliseconds}", "type": "button_press",
                     "attributes": {"source": "front_door", "source_type": "devices", "timestamp": milliseconds}},
        }
        return self.post("/webhooks/ring", webhook)[1]["event_id"]

    def get(self, path):
        return call("GET", self.base + path, None, self.token)

    def post(self, path, payload=None):
        return call("POST", self.base + path, payload if payload is not None else {}, self.token)

    def beat(self, number, title, narration):
        print(f"\n=== BEAT {number}: {title}")
        print(f"    say: {narration}")
        time.sleep(self.pace)

    def show(self, label, value):
        print(f"    {label:<26} {value}")

    def simulate(self, fixture):
        status, data = self.post(f"/api/simulate?fixture={fixture}")
        if status != 200:
            raise SystemExit(f"simulate {fixture} failed: {status} {data}")
        return data["event_id"]

    def wait_event(self, event_id, timeout=10):
        deadline = time.time() + timeout
        while time.time() < deadline:
            status, event = self.get(f"/api/events/{event_id}")
            if status == 200 and event.get("status") in {"enriched", "enrichment_failed"}:
                return event
            time.sleep(0.2)
        raise SystemExit(f"event {event_id} never reached a terminal status")

    def escalation_rows(self, event_id):
        _, data = self.get("/api/escalation/log")
        return [row for row in data.get("log", []) if row.get("event_id") == event_id]

    def mcp_call(self, name, arguments):
        status, data = self.post(
            "/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}},
        )
        if status != 200 or "result" not in data:
            return {"error": data}
        text = data["result"]["content"][0]["text"]
        return safe_json(text)


def run_intro(demo, args):
    print(f"\nAccessBell demo -> {demo.base}")
    if args.token:
        print("    auth: Bearer token")
    _, health = demo.get("/health")
    print(f"    health: {health}")
    if args.reset_hint:
        print("    tip: start the server with a fresh DB_URL so counters match the screen")


def beat_generic(demo):
    demo.beat(1, "See + Understand (no invention)",
              "Ring - and within 200 ms the biggest screen says someone is at the door. It does not guess.")
    if demo.calendar_mode:
        demo.show("note", "calendar join is on - using an off-window ring so 'generic' stays honest")
        event = demo.wait_event(demo.bare_ring(OPEN_EVENT_TIME, OPEN_EVENT_MS, "demo-generic"))
    else:
        event = demo.wait_event(demo.simulate("doorbell_unknown"))
    triage = event["triage"]
    demo.show("category / grounding", f"{triage.get('category')} / {triage.get('grounding')}")
    demo.show("caption EN", triage.get("caption_en"))
    demo.show("caption VI", triage.get("caption_vi"))
    demo.show("why EN", event["why"]["en"])
    demo.show("child caption", (event.get("caption_child") or {}).get("en"))
    demo.show("evidence", triage.get("evidence"))


def beat_grounded(demo):
    demo.beat(2, "Door calendar (J1) turns a ring into meaning",
              "Say 'expect pharmacy around ten' and the next ring explains itself, in both languages.")
    if demo.calendar_mode:
        demo.show("note", "using a package window at 14:30 so the calendar stub cannot cover it up")
        demo.post("/api/expected", PACKAGE_WINDOW)
        fixture = "doorbell_package_window"
    else:
        demo.post("/api/expected", PHARMACY_WINDOW)
        fixture = "doorbell_med"
    _, windows = demo.get("/api/expected")
    demo.show("door calendar", [w["label"] for w in windows.get("windows", [])])
    event = demo.wait_event(demo.simulate(fixture))
    triage = event["triage"]
    demo.show("category / grounding", f"{triage.get('category')} / {triage.get('grounding')}")
    demo.show("evidence", triage.get("evidence"))
    demo.show("why EN", event["why"]["en"])
    demo.show("why VI", event["why"]["vi"])
    return event


def beat_act(demo, event):
    demo.beat(3, "Act from where you already are",
              "An never touches a phone: TV remote, two big buttons.")
    status, data = demo.post(f"/api/events/{event['id']}/reply", {"action": "leave_at_door", "source": "pwa"})
    demo.show("reply accepted", f"{status} {data}")


def beat_protect(demo, args):
    demo.beat(4, "Protect: consent escalation, audited and revocable",
              "If nobody answers in time, Lan hears about it - and the audit trail proves it.")
    demo.post("/api/escalation/contacts", {"label": "Lan", "recipient": "lan@example.com"})
    demo.post("/api/escalation/policy", {"enabled": True, "timeout_seconds": args.timeout, "min_urgency": 7})
    _, policy = demo.get("/api/escalation/policy")
    demo.show("policy", policy)

    if args.escalate in {"stop", "both"}:
        stopped_id = demo.wait_event(demo.simulate("doorbell_med"))["id"]
        time.sleep(min(2, args.timeout / 2))
        demo.show("on screen", "countdown + Stop button are visible on the TV right now")
        demo.post("/api/escalation/stop", {"event_id": stopped_id, "source": "pwa"})
        rows = demo.escalation_rows(stopped_id)
        demo.show("audit (stopped)", [row["status"] for row in rows])

    if args.escalate in {"fire", "both"}:
        demo.post("/api/escalation/policy", {"enabled": True, "timeout_seconds": 3, "min_urgency": 7})
        fired_id = demo.wait_event(demo.simulate("doorbell_med"))["id"]
        time.sleep(5)
        rows = demo.escalation_rows(fired_id)
        demo.show("audit (queued)", [row["status"] for row in rows])
        if rows:
            demo.show("audit message", rows[0]["message"][:104])
    demo.post("/api/escalation/policy", {"enabled": False})


def beat_ask(demo, args):
    demo.beat(5, "Ask: the door answers out loud", "What came today? The door answers with receipts.")
    _, tools = demo.post("/mcp", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    demo.show("mcp tools", len(tools.get("result", {}).get("tools", [])))
    brief = demo.get(f"/api/brief?date={args.date}&lang=vi")[1]
    demo.show("brief VI", brief.get("bullets", [])[:3])
    detail = demo.mcp_call("get_context_snapshot", {"event_id": demo.get("/api/events?limit=1")[1]["events"][0]["id"]})
    demo.show("context snapshot", f"calendar={detail.get('calendar_configured')} "
                                  f"labels={[w['label'] for w in detail.get('expected_context', [])]}")


def beat_advise(demo):
    demo.beat(6, "Advisor: suggests, never writes", "The system notices a pattern and offers to set a window.")
    data = demo.get("/api/advise")[1]
    demo.show("read_only / auto_write", f"{data.get('read_only')} / {data.get('auto_write')}")
    demo.show("suggestions", [item.get("reason") for item in data.get("suggestions", [])])


def beat_share(demo, args):
    demo.beat(7, "Share: preview, consent, log, revoke", "Sharing is opt-in, logged, and one click to take back.")
    preview = demo.post("/api/share/preview", {"consent": False, "recipient": "son@example.com", "date": args.date})[1]
    demo.show("requires consent", preview.get("requires_consent"))
    shared = demo.post("/api/share", {"consent": True, "recipient": "son@example.com", "date": args.date})[1]
    demo.show("share logged", shared.get("share_id"))
    demo.post(f"/api/share/{shared['share_id']}/revoke", {})
    _, log = demo.get("/api/share/log")
    demo.show("audit rows", [row["message"].split("\n")[0][:48] for row in log.get("log", [])[:2]])


def beat_proof(demo):
    demo.beat(8, "Proof", "The gate is measurable, and every alert row carries the policy it ran under.")
    metrics = demo.get("/api/metrics")[1]
    demo.show("grounding counters", metrics.get("grounding"))
    demo.show("tier1_ms", (metrics.get("timers") or {}).get("tier1_ms"))
    demo.show("context_ms", (metrics.get("timers") or {}).get("context_ms"))
    demo.show("escalation status", metrics.get("escalation_status"))
    policy = demo.get("/api/policy")[1]
    demo.show("policy", f"v{policy.get('version')} sha {policy.get('short')}")
    demo.show("run also", "scripts/ablation_evidence.py  (event_only 0.5 -> with evidence 1.0)")


def beat_calendar(demo, args):
    if not args.calendar:
        return
    demo.beat(9, "Multi-MCP household (J2): the calendar is not ours",
              "A separate Calendar MCP holds the schedule; AccessBell only borrows it as evidence.")
    status, created = call("POST", args.calendar, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "create_event", "arguments": CALENDAR_EVENT},
    })
    demo.show("calendar create_event", f"{status} {created.get('result', created)}")
    request_id = f"demo-j2-{uuid4().hex[:8]}"
    webhook = {
        "meta": {"version": "1.1", "time": CALM_EVENT_TIME, "request_id": request_id, "account_id": "ava1.ring.account.demo"},
        "data": {"id": f"front_door_button_press_{CALM_EVENT_MS}", "type": "button_press",
                 "attributes": {"source": "front_door", "source_type": "devices", "timestamp": CALM_EVENT_MS}},
    }
    event = demo.wait_event(demo.post("/webhooks/ring", webhook)[1]["event_id"])
    triage = event["triage"]
    demo.show("context_status", triage.get("context_status"))
    demo.show("evidence", triage.get("evidence"))
    demo.show("why EN", event["why"]["en"])
    if triage.get("context_status") == "disabled":
        print("    WARN  app has no CALENDAR_MCP_URL - restart it with the join enabled to see this beat")


def beat_demotion(demo, args):
    if not args.demote:
        return
    demo.beat(10, "Evidence gate under a live model",
              "A real model wants to name the package. Our code says: no evidence, no claim.")
    request_id = f"demo-d-{uuid4().hex[:8]}"
    webhook = {
        "meta": {"version": "1.1", "time": OPEN_EVENT_TIME, "request_id": request_id, "account_id": "ava1.ring.account.demo"},
        "data": {"id": f"front_door_button_press_{OPEN_EVENT_MS}", "type": "button_press",
                 "attributes": {"source": "front_door", "source_type": "devices", "timestamp": OPEN_EVENT_MS}},
    }
    event = demo.wait_event(demo.post("/webhooks/ring", webhook)[1]["event_id"])
    triage = event["triage"]
    demo.show("category / grounding", f"{triage.get('category')} / {triage.get('grounding')}")
    demo.show("why EN", event["why"]["en"])
    if triage.get("grounding") != "demoted_insufficient_evidence":
        print("    note  the model did not over-claim this run - rerun, or show tests/test_adversarial.py instead")


def main():
    parser = argparse.ArgumentParser(description="Run the AccessBell demo story")
    parser.add_argument("--url", default=os.getenv("ACCESSBELL_URL", "http://localhost:8080"))
    parser.add_argument("--token", default=os.getenv("API_TOKEN", ""))
    parser.add_argument("--pace", type=float, default=3.0, help="seconds to hold each beat on camera")
    parser.add_argument("--date", default="2026-09-15", help="brief date used by the story")
    parser.add_argument("--timeout", type=int, default=20, help="escalation timeout seconds for the countdown shot")
    parser.add_argument("--escalate", choices=("both", "stop", "fire", "off"), default="both")
    parser.add_argument("--calendar", default="", help="Calendar MCP URL, e.g. http://127.0.0.1:8085/mcp")
    parser.add_argument("--demote", action="store_true", help="add the live-model demotion beat (needs a real LLM)")
    parser.add_argument("--reset-hint", action="store_true")
    args = parser.parse_args()

    demo = Demo(args)
    run_intro(demo, args)
    beat_generic(demo)
    event = beat_grounded(demo)
    beat_act(demo, event)
    if args.escalate != "off":
        beat_protect(demo, args)
    beat_ask(demo, args)
    beat_advise(demo)
    beat_share(demo, args)
    beat_proof(demo)
    beat_calendar(demo, args)
    beat_demotion(demo, args)
    print("\nDone. Fast path never waits for smart path; smart path never invents.")


if __name__ == "__main__":
    main()
