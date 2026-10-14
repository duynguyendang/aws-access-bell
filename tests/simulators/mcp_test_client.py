import asyncio
import os
import uuid
from typing import Optional

import httpx


class MCPTestClient:
    def __init__(self, mcp_url: str = "http://localhost:8080/mcp", auth_token: str = ""):
        self.mcp_url = os.getenv("MCP_URL", mcp_url)
        self.auth_token = auth_token or os.getenv("MCP_HTTP_TOKEN", "change-me")
        self.session_id: Optional[str] = None

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    async def initialize(self) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {
                    "tools": {"listChanged": True},
                },
                "clientInfo": {
                    "name": "AccessBell-E2E-Test",
                    "version": "1.0.0",
                },
            },
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.mcp_url,
                json=payload,
                headers=self._headers(),
                timeout=10.0,
            )

        result = response.json()
        if "result" in result and "sessionId" in result.get("result", {}):
            self.session_id = result["result"]["sessionId"]
        return result

    async def list_tools(self) -> list[dict]:
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/list",
            "params": {},
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.mcp_url,
                json=payload,
                headers=self._headers(),
                timeout=10.0,
            )

        result = response.json()
        return result.get("result", {}).get("tools", [])

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.mcp_url,
                json=payload,
                headers=self._headers(),
                timeout=30.0,
            )

        return response.json()

    async def test_all_tools(self) -> dict:
        results = {}
        print("1. Initializing MCP session...")
        init_result = await self.initialize()
        results["initialize"] = init_result
        print(f"   Session: {self.session_id or 'stateless'}")

        print("2. Listing available tools...")
        tools = await self.list_tools()
        results["tools"] = [t["name"] for t in tools]
        print(f"   Found {len(tools)} tools: {[t['name'] for t in tools]}")

        latest_event_id = None
        if "get_door_alerts" in results["tools"]:
            print("3. Testing get_door_alerts...")
            r = await self.call_tool("get_door_alerts", {
                "urgency_min": 0,
            })
            results["get_door_alerts"] = r
            content = r.get("result", {}).get("content", [{}])
            text = content[0].get("text", "") if content else ""
            print(f"   Response: {text[:200]}")
            try:
                data = json.loads(text)
                alerts = data.get("alerts", [])
                if alerts:
                    latest_event_id = alerts[0].get("event_id")
            except Exception:
                pass

        if "get_daily_summary" in results["tools"]:
            print("4. Testing get_daily_summary...")
            r = await self.call_tool("get_daily_summary", {})
            results["get_daily_summary"] = r
            content = r.get("result", {}).get("content", [{}])
            text = content[0].get("text", "") if content else ""
            print(f"   Summary: {text[:200]}")

        if latest_event_id is not None and "get_event_detail" in results["tools"]:
            print(f"5. Testing get_event_detail (event_id={latest_event_id})...")
            r = await self.call_tool("get_event_detail", {
                "event_id": latest_event_id,
            })
            results["get_event_detail"] = r
            print("   Done")

        if latest_event_id is not None and ("send_quick_reply" in results["tools"] or "send_door_response" in results["tools"]):
            tool_name = "send_quick_reply" if "send_quick_reply" in results["tools"] else "send_door_response"
            print(f"6. Testing {tool_name} (event_id={latest_event_id})...")
            r = await self.call_tool(tool_name, {
                "event_id": latest_event_id,
                "action": "leave_at_door",
            })
            results["send_door_response"] = r
            print("   Done")

        return results


async def quick_test(mcp_url: str = "http://localhost:8080/mcp"):
    client = MCPTestClient(mcp_url=mcp_url)
    return await client.test_all_tools()


if __name__ == "__main__":
    asyncio.run(quick_test())
