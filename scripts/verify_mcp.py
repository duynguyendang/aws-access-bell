"""Verify /mcp end-to-end with a JSON-RPC session: initialize, tools/list, tools/call.

Boots the app on a free port unless --url points at a running server, then sends
an unauthenticated request (bare-401 asserted only on the server it boots itself)
followed by a full initialize / tools/list / tools/call round. Prints every step
so the transcript can be kept as evidence; exits non-zero when a check fails.

Usage: python scripts/verify_mcp.py [--url http://127.0.0.1:8080] [--token TOKEN]
       [--api-token TOKEN] [--record FILE]
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_TOKEN = "verify-mcp-token"
EXPECTED_TOOLS = 11


def _parse(raw: bytes):
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def request(url: str, body: dict | None = None, token: str = "", method: str = "POST"):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("content-type", "application/json")
    if token:
        req.add_header("authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.status, dict(response.headers), _parse(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), _parse(exc.read())


def rpc(url: str, method: str, params: dict | None = None, request_id: int = 1, token: str = ""):
    body = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        body["params"] = params
    return request(f"{url}/mcp", body, token=token)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_healthy(url: str, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            status, _, _ = request(f"{url}/health", method="GET")
            if status == 200:
                return True
        except OSError:
            pass
        time.sleep(0.5)
    return False


def start_server(port: int) -> subprocess.Popen:
    env = dict(os.environ)
    env.update(
        {
            "APP_ENV": "development",
            "MOCK_MODE": "true",
            "API_AUTH_DISABLED": "true",
            "MCP_HTTP_TOKEN": DEFAULT_TOKEN,
            "MCP_401_WWW_AUTHENTICATE": "false",
            "PORT": str(port),
            "DB_URL": f"sqlite:///{Path(tempfile.mkdtemp()) / 'verify_mcp.db'}",
            "RATE_LIMIT_PER_MINUTE": "1000",
        }
    )
    return subprocess.Popen(
        [sys.executable, "-m", "backend"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="", help="target a running server instead of booting one")
    parser.add_argument("--token", default="", help="MCP bearer token (default: %s when booting)" % DEFAULT_TOKEN)
    parser.add_argument("--api-token", default="", help="API bearer token for /api/simulate on the target")
    parser.add_argument("--record", default="", help="write the transcript to this file")
    args = parser.parse_args()

    lines: list[str] = []
    failures: list[str] = []

    def log(message: str):
        lines.append(message)
        print(message)

    def check(condition: bool, ok_message: str, fail_message: str):
        if condition:
            log(f"ok   {ok_message}")
        else:
            failures.append(fail_message)
            log(f"FAIL {fail_message}")

    server = None
    if args.url:
        url = args.url.rstrip("/")
        token = args.token
    else:
        port = free_port()
        url = f"http://127.0.0.1:{port}"
        token = args.token or DEFAULT_TOKEN
        server = start_server(port)

    try:
        if server is not None and not wait_healthy(url):
            failures.append("server did not become healthy")
            log("FAIL server did not become healthy")
        else:
            if server is not None:
                log(f"server up at {url} (mock events, bare-401 mode, token required)")

            status, headers, _ = rpc(url, "initialize", {"protocolVersion": "2025-11-25"})
            lower_headers = {key.lower(): value for key, value in headers.items()}
            if server is not None:
                check(
                    status == 401 and "www-authenticate" not in lower_headers,
                    "unauthenticated /mcp answers a bare 401 (no WWW-Authenticate, Alexa+ mode)",
                    f"expected bare 401 without a token, got {status} headers={lower_headers}",
                )
            else:
                log(
                    f"note unauthenticated /mcp answered {status}"
                    f" (WWW-Authenticate {'present' if 'www-authenticate' in lower_headers else 'absent'})"
                )

            status, _, body = rpc(url, "initialize", {"protocolVersion": "2025-11-25"}, token=token)
            result = (body or {}).get("result") or {}
            server_info = result.get("serverInfo") or {}
            check(
                status == 200 and server_info.get("name") == "accessbell-mcp",
                f"initialize negotiated protocol {result.get('protocolVersion')} with {server_info.get('name')}",
                f"initialize failed: status={status} result={result}",
            )

            rpc(url, "notifications/initialized", token=token)

            status, _, body = rpc(url, "tools/list", request_id=2, token=token)
            tools = ((body or {}).get("result") or {}).get("tools") or []
            names = [tool.get("name") for tool in tools]
            check(
                status == 200
                and len(tools) == EXPECTED_TOOLS
                and len(set(names)) == EXPECTED_TOOLS
                and all(tool.get("inputSchema") for tool in tools),
                f"tools/list returns {len(tools)} unique tools, all with input schemas",
                f"tools/list expected {EXPECTED_TOOLS} tools with schemas, got {len(tools)}: {names}",
            )

            request(f"{url}/api/simulate?fixture=doorbell_med", token=args.api_token)
            time.sleep(0.5)
            status, _, body = rpc(
                url,
                "tools/call",
                {"name": "get_door_alerts", "arguments": {"limit": 5}},
                request_id=3,
                token=token,
            )
            content = ((body or {}).get("result") or {}).get("content") or []
            payload = _parse((content[0].get("text") or "").encode("utf-8")) if content else None
            alerts = (payload or {}).get("alerts") if isinstance(payload, dict) else None
            check(
                status == 200 and bool(alerts),
                f"tools/call get_door_alerts returned {len(alerts or [])} alert(s)",
                f"tools/call did not return alerts: status={status} body={body}",
            )
    except OSError as exc:
        failures.append(f"cannot reach {url}: {exc}")
        log(f"FAIL cannot reach {url}: {exc}")
    finally:
        if server is not None:
            try:
                server.terminate()
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
            except OSError:
                pass

    if args.record:
        Path(args.record).write_text("\n".join(lines) + "\n", encoding="utf-8")
    if failures:
        return 1
    log("MCP verification OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
