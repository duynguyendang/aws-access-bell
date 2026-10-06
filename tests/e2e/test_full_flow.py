import asyncio
import os
import time
import httpx

from tests.simulators.ring_simulator import RingSimulator, SCENARIOS
from tests.simulators.firetv_client import FireTVSimulator
from tests.simulators.alexa_simulator import AlexaSimulator
from tests.simulators.mcp_test_client import MCPTestClient


async def _wait_for_alert(firetv, event_id, alert_type=None, timeout=6.0):
    deadline = time.monotonic() + timeout
    target = str(event_id)
    while time.monotonic() < deadline:
        for alert in firetv.alerts:
            if str(alert.event_id) == target or str(getattr(alert, "internal_event_id", "")) == target:
                if alert_type is None or alert.alert_type == alert_type:
                    return alert
        await asyncio.sleep(0.1)
    return None


def test_backend_health(live_server):
    with httpx.Client() as client:
        r = client.get(f"{live_server}/health", timeout=5.0)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_firetv_sse_connection(live_server):
    async def _run():
        sim = FireTVSimulator(base_url=live_server)
        await sim.connect()
        assert sim.connected, "Fire TV SSE not connected"
        await sim.disconnect()

    asyncio.run(_run())


def test_mcp_server_init(live_server):
    async def _run():
        mcp = MCPTestClient(mcp_url=f"{live_server}/mcp")
        result = await mcp.initialize()
        assert "result" in result or "error" not in result
        tools = await mcp.list_tools()
        tool_names = [t["name"] for t in tools]
        expected = {"get_door_alerts", "get_daily_summary"}
        assert expected.issubset(set(tool_names)), f"Missing tools: {expected - set(tool_names)}"

    asyncio.run(_run())


def test_full_flow_package_delivery(live_server):
    async def _run():
        firetv = FireTVSimulator(base_url=live_server)
        await firetv.connect()
        try:
            alexa = AlexaSimulator(use_tts=False)
            ring = RingSimulator(base_url=live_server)
            scenario = SCENARIOS["package_delivery"]

            send_result = await ring.send_doorbell_press(
                snapshot_key=scenario["snapshot_key"],
                expected_label=scenario["expected_label"],
            )
            event_id = send_result["event_id"]
            assert send_result["http_status"] in (200, 202)

            tier1_alert = await asyncio.wait_for(
                _wait_for_alert(firetv, event_id, alert_type="tier1_raw"),
                timeout=4.0,
            )
            assert tier1_alert is not None

            auth_headers = {}
            if os.getenv("API_TOKEN"):
                auth_headers["Authorization"] = f"Bearer {os.getenv('API_TOKEN')}"

            tier2_alert = await asyncio.wait_for(
                _wait_for_alert(firetv, event_id, alert_type="tier2_enriched"),
                timeout=6.0,
            )
            assert tier2_alert is not None
            assert tier2_alert.label in (scenario["expected_label"], "UNKNOWN_VISITOR")

            await alexa.announce(
                event_id=event_id,
                text=tier2_alert.message,
                language="en",
            )

            async with httpx.AsyncClient() as client:
                r = await client.get(f"{live_server}/api/events/{event_id}", headers=auth_headers, timeout=5.0)
            assert r.status_code == 200
            event_data = r.json()
            assert event_data["classification"]["label"] in (scenario["expected_label"], "UNKNOWN_VISITOR")
        finally:
            await firetv.disconnect()

    asyncio.run(_run())


def test_full_flow_med_delivery(live_server):
    async def _run():
        firetv = FireTVSimulator(base_url=live_server)
        await firetv.connect()
        try:
            alexa = AlexaSimulator(use_tts=False)
            ring = RingSimulator(base_url=live_server)
            scenario = SCENARIOS["med_delivery"]

            send_result = await ring.send_doorbell_press(
                snapshot_key=scenario["snapshot_key"],
                expected_label=scenario["expected_label"],
            )
            event_id = send_result["event_id"]

            tier2_alert = await asyncio.wait_for(
                _wait_for_alert(firetv, event_id, alert_type="tier2_enriched"),
                timeout=6.0,
            )

            assert tier2_alert is not None
            assert tier2_alert.label in ("MED_DELIVERY", "UNKNOWN_VISITOR")

            await alexa.announce(event_id, tier2_alert.message, "en")
        finally:
            await firetv.disconnect()

    asyncio.run(_run())


def test_debounce(live_server):
    async def _run():
        firetv = FireTVSimulator(base_url=live_server)
        await firetv.connect()
        try:
            ring = RingSimulator(base_url=live_server)
            results = await ring.send_debounce_burst(count=3, interval_ms=100)
            await asyncio.sleep(2)
            event_ids = [r["event_id"] for r in results]
            alerts = [a for a in firetv.alerts if a.event_id in event_ids]
            tier2_events = set(a.event_id for a in alerts if a.alert_type == "tier2_enriched")
            assert len(tier2_events) <= 2
        finally:
            await firetv.disconnect()

    asyncio.run(_run())


def test_mcp_query_after_events(live_server):
    async def _run():
        mcp = MCPTestClient(mcp_url=f"{live_server}/mcp")
        result = await mcp.call_tool("get_door_alerts", {
            "urgency_level": 2,
            "time_range": "last_24h",
        })
        content = result.get("result", {}).get("content", [])
        assert len(content) > 0

    asyncio.run(_run())


def test_mcp_daily_summary(live_server):
    async def _run():
        mcp = MCPTestClient(mcp_url=f"{live_server}/mcp")
        result = await mcp.call_tool("get_daily_summary", {})
        content = result.get("result", {}).get("content", [])
        assert len(content) > 0

    asyncio.run(_run())


def test_quick_reply(live_server):
    headers = {}
    token = os.getenv("API_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with httpx.Client() as client:
        r = client.post(
            f"{live_server}/api/events/evt_sim_test/quick-reply",
            json={"template": "please_leave_at_door"},
            headers=headers,
            timeout=5.0,
        )
    assert r.status_code in (200, 202)
