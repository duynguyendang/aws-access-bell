import asyncio
import os
import socket
import threading
import time
import httpx
import pytest
import uvicorn

from backend.main import app


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


class UvicornServerThread(threading.Thread):
    def __init__(self, host: str, port: int):
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        config = uvicorn.Config(app, host=host, port=port, log_level="warning")
        self.server = uvicorn.Server(config)

    def run(self):
        self.server.run()

    def stop(self):
        self.server.should_exit = True


@pytest.fixture(scope="session")
def live_server():
    env_base = os.getenv("BASE_URL")
    if env_base:
        base_url = env_base.rstrip("/")
        os.environ["BASE_URL"] = base_url
        os.environ.setdefault("MCP_URL", f"{base_url}/mcp")
        yield base_url
        return

    host = "127.0.0.1"
    port = int(os.getenv("PORT", "8080"))
    base_url = f"http://{host}:{port}"
    server_thread = None

    if not _port_open(host, port):
        server_thread = UvicornServerThread(host, port)
        server_thread.start()
        # Wait for healthcheck
        ready = False
        for _ in range(50):
            try:
                with httpx.Client(timeout=1.0) as client:
                    res = client.get(f"{base_url}/health")
                    if res.status_code == 200:
                        ready = True
                        break
            except Exception:
                time.sleep(0.1)
        if not ready:
            raise RuntimeError(f"Server on {base_url} did not become ready")

    os.environ["BASE_URL"] = base_url
    os.environ["MCP_URL"] = f"{base_url}/mcp"
    yield base_url

    if server_thread is not None:
        server_thread.stop()
