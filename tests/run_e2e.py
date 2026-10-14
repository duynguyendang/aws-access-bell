import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx

from tests.simulators.ring_simulator import RingSimulator, SCENARIOS
from tests.simulators.firetv_client import FireTVSimulator
from tests.simulators.alexa_simulator import AlexaSimulator
from tests.simulators.mcp_test_client import MCPTestClient

DEFAULT_BASE = os.getenv("BASE_URL", "http://localhost:8080")
DEFAULT_MCP = os.getenv("MCP_URL", f"{DEFAULT_BASE}/mcp")


async def run_full_demo(base_url: str = DEFAULT_BASE, mcp_url: str = DEFAULT_MCP):
    print("=" * 60)
    print("AccessBell E2E Full Flow Test with Simulated Devices")
    print("Ring -> AccessBell -> Fire TV + Alexa + MCP")
    print("=" * 60)

    print("Step 0: Checking backend health...")
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(f"{base_url}/health", timeout=5.0)
            print(f"Backend OK: {r.json()}")
        except Exception as exc:
            print(f"Backend connection failed: {exc}")
            print(f"Please ensure AccessBell server is running on {base_url}")
            return

    print("\nStep 1: Connecting Fire TV simulator (SSE)...")
    firetv = FireTVSimulator(base_url=base_url)
    await firetv.connect()
    if firetv.connected:
        print("Fire TV SSE connected.")
    else:
        print("Fire TV SSE connection failed.")
        return

    print("\nStep 2: Initializing Alexa simulator...")
    alexa = AlexaSimulator(use_tts=True)
    print(f"Alexa ready (TTS available: {alexa._tts_available})")

    print("\nStep 3: Initializing MCP client...")
    mcp = MCPTestClient(mcp_url=mcp_url)
    try:
        await mcp.initialize()
        tools = await mcp.list_tools()
        tool_names = [t["name"] for t in tools]
        print(f"MCP connected. Available tools: {tool_names}")
    except Exception as exc:
        print(f"MCP warning: {exc}")
        mcp = None

    print("\nStep 4: Running scenarios...")
    ring = RingSimulator(base_url=base_url)

    for scenario_name, scenario in SCENARIOS.items():
        print(f"\nScenario: {scenario_name.upper()}")
        result = await ring.send_doorbell_press(
            snapshot_key=scenario["snapshot_key"],
            expected_label=scenario["expected_label"],
        )
        event_id = result["event_id"]
        print(f"Sent: HTTP {result['http_status']} | event_id={event_id}")

        await asyncio.sleep(3)

        alerts = firetv.get_alerts_for_event(event_id)
        if alerts:
            for a in alerts:
                print(f"TV Alert: [{a.alert_type}] {a.label} | urgency={a.urgency} | {a.latency_ms:.0f}ms")
            last_alert = alerts[-1]
            await alexa.announce(event_id, last_alert.message, "en")
        else:
            print(f"No Fire TV alert received for {event_id}")

        await asyncio.sleep(1)

    if mcp:
        print("\nStep 5: Querying MCP after events...")
        r = await mcp.call_tool("get_door_alerts", {
            "urgency_min": 2,
        })
        content = r.get("result", {}).get("content", [{}])
        if content:
            print(f"get_door_alerts: {content[0].get('text', '')[:200]}")

        r = await mcp.call_tool("get_daily_summary", {})
        content = r.get("result", {}).get("content", [{}])
        if content:
            print(f"get_daily_summary: {content[0].get('text', '')[:200]}")

    print("\n" + "=" * 60)
    print("Summary:")
    print(f"Ring events sent: {len(ring.sent_events)}")
    print(f"Fire TV alerts:   {len(firetv.alerts)}")
    print(f"Alexa utterances: {len(alexa.utterances)}")

    label_counts = {}
    for a in firetv.alerts:
        if a.alert_type == "tier2_enriched":
            label_counts[a.label] = label_counts.get(a.label, 0) + 1
    print(f"Classifications:  {json.dumps(label_counts, indent=2)}")

    tier1_latencies = [a.latency_ms for a in firetv.alerts if a.alert_type == "tier1_raw" and a.latency_ms > 0]
    tier2_latencies = [a.latency_ms for a in firetv.alerts if a.alert_type == "tier2_enriched" and a.latency_ms > 0]

    if tier1_latencies:
        print(f"Tier 1 median latency: {sorted(tier1_latencies)[len(tier1_latencies)//2]:.0f}ms")
    if tier2_latencies:
        print(f"Tier 2 median latency: {sorted(tier2_latencies)[len(tier2_latencies)//2]:.0f}ms")

    print("\nE2E demo finished.")
    await firetv.disconnect()


if __name__ == "__main__":
    asyncio.run(run_full_demo())
