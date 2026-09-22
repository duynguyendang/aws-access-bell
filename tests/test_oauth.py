import json
import os
import time
import threading
import uuid
from base64 import urlsafe_b64encode
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault("LLM_PROVIDER", "stub")
if "DB_URL" not in os.environ:
    os.environ["DB_URL"] = f"sqlite:////tmp/accessbell_oauth_{uuid.uuid4().hex}.db"
if "RATE_LIMIT_PER_MINUTE" not in os.environ:
    os.environ["RATE_LIMIT_PER_MINUTE"] = "1000"

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from backend import main as main_module
from backend.config import settings
from backend.oauth import OAuthVerifier

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

AUDIENCE = "accessbell-demo"
RESOURCE = "https://accessbell-demo/mcp"


def _fmt_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return urlsafe_b64encode(raw).rstrip(b"=").decode()


def _make_jwk(key, kid: str) -> dict:
    numbers = key.public_key().public_numbers()
    return {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "alg": "RS256",
        "n": _fmt_uint(numbers.n),
        "e": _fmt_uint(numbers.e),
    }


class StubIdP:
    def __init__(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = "test-kid"
        self.jwk = _make_jwk(self.key, self.kid)
        handler = self._handler()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def _handler(self):
        def make_handler():
            idp = self

            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    if self.path == "/jwks":
                        self._json({"keys": [idp.jwk]})
                    elif self.path == "/.well-known/oauth-authorization-server":
                        self._json({"issuer": idp.base_url, "jwks_uri": f"{idp.base_url}/jwks"})
                    else:
                        self.send_response(404)
                        self.end_headers()

                def _json(self, payload: dict):
                    body = json.dumps(payload).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def log_message(self, *_args):
                    pass

            return Handler

        return make_handler()

    def sign(self, scope: str, *, resource=RESOURCE, include_resource=True, aud=AUDIENCE, iss=None, exp=3600):
        claims = {"iss": iss or self.base_url, "aud": aud, "scope": scope, "exp": int(time.time()) + exp}
        if include_resource:
            claims["resource"] = resource
        return pyjwt.encode(claims, self.key, algorithm="RS256", headers={"kid": self.kid})

    def stop(self):
        self.server.shutdown()

    @property
    def service_token(self) -> str:
        return self.sign("mcp:service")

    @property
    def user_token(self) -> str:
        return self.sign("mcp:tools mcp:resources")


@pytest.fixture(scope="module")
def idp():
    identity = StubIdP()
    yield identity
    identity.stop()


@pytest.fixture(scope="module")
def client():
    with TestClient(main_module.app) as test_client:
        yield test_client


@pytest.fixture
def verifier(idp, monkeypatch):
    monkeypatch.setattr(settings, "oauth_issuer", idp.base_url)
    monkeypatch.setattr(settings, "oauth_jwks_url", f"{idp.base_url}/jwks")
    monkeypatch.setattr(settings, "oauth_audience", AUDIENCE)
    monkeypatch.setattr(settings, "mcp_resource", RESOURCE)
    monkeypatch.setattr(settings, "oauth_require_resource", False)
    monkeypatch.setattr(settings, "mcp_http_token", "")
    return OAuthVerifier(settings)


def test_verifier_disabled_by_default():
    assert OAuthVerifier(settings).enabled is False


def test_metadata(idp, verifier):
    meta = verifier.protected_resource_metadata()
    assert meta["resource"] == RESOURCE
    assert idp.base_url in meta["authorization_servers"]
    assert "mcp:service" in meta["scopes_supported"]


def test_service_token_verifies(verifier, idp):
    context = verifier.authenticate(f"Bearer {idp.service_token}")
    assert context is not None and context.scope == "service"
    assert context.can_act_for_user is False


def test_user_token_verifies(verifier, idp):
    context = verifier.authenticate(f"Bearer {idp.user_token}")
    assert context is not None and context.scope == "user"
    assert context.can_act_for_user is True


def test_missing_or_malformed_header(verifier):
    assert verifier.authenticate("") is None
    assert verifier.authenticate("Basic abc") is None
    assert verifier.authenticate("Bearer") is None


def test_expired_token_rejected(verifier, idp):
    token = idp.sign(scope="mcp:service", exp=-100)
    assert verifier.authenticate(f"Bearer {token}") is None


def test_wrong_audience_rejected(verifier, idp):
    token = idp.sign(scope="mcp:service", aud="someone-else")
    assert verifier.authenticate(f"Bearer {token}") is None


def test_wrong_issuer_rejected(verifier, idp):
    token = idp.sign(scope="mcp:service", iss="https://evil.example")
    assert verifier.authenticate(f"Bearer {token}") is None


def test_unknown_scope_rejected(verifier, idp):
    token = idp.sign(scope="something:else")
    assert verifier.authenticate(f"Bearer {token}") is None


def test_missing_resource_claim_when_required(verifier, idp, monkeypatch):
    monkeypatch.setattr(settings, "oauth_require_resource", True)
    token = idp.sign(scope="mcp:service", include_resource=False)
    assert verifier.authenticate(f"Bearer {token}") is None
    monkeypatch.setattr(settings, "oauth_require_resource", False)
    assert verifier.authenticate(f"Bearer {token}") is not None


def test_wrong_resource_claim_rejected(verifier, idp, monkeypatch):
    monkeypatch.setattr(settings, "oauth_require_resource", True)
    token = idp.sign(scope="mcp:service", resource="https://other/mcp")
    assert verifier.authenticate(f"Bearer {token}") is None
    monkeypatch.setattr(settings, "oauth_require_resource", False)


def test_discovery_endpoint(client):
    body = client.get("/.well-known/oauth-protected-resource").json()
    assert "scopes_supported" in body


def test_endpoint_401_without_token(verifier, client):
    resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert resp.status_code == 401
    challenge = resp.headers.get("www-authenticate", "")
    assert "resource_metadata=" in challenge
    assert "/.well-known/oauth-protected-resource" in challenge


def test_cf_access_jwt_header_is_user_tier(verifier, idp, client, monkeypatch):
    monkeypatch.setattr(settings, "cf_access_jwt_enabled", True)
    token = idp.sign("", include_resource=False)
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {"name": "get_daily_summary", "arguments": {}},
        },
        headers={"CF-Access-Jwt-Assertion": token},
    )
    assert resp.status_code == 200


def test_cf_access_header_ignored_when_disabled(verifier, idp, client):
    token = idp.sign("", include_resource=False)
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 9, "method": "ping"},
        headers={"CF-Access-Jwt-Assertion": token},
    )
    assert resp.status_code == 401


def test_service_token_can_list_but_not_act(verifier, idp, client):
    headers = {"Authorization": f"Bearer {idp.service_token}"}
    listed = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()["result"]["tools"]) == 11
    acted = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_daily_summary", "arguments": {}}},
        headers=headers,
    )
    assert acted.status_code == 403


def test_user_token_can_act(verifier, idp, client):
    resp = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "get_daily_summary", "arguments": {}}},
        headers={"Authorization": f"Bearer {idp.user_token}"},
    )
    assert resp.status_code == 200
    data = json.loads(resp.json()["result"]["content"][0]["text"])
    assert "bullets" in data


def test_expired_token_at_endpoint(verifier, idp, client):
    token = idp.sign(scope="mcp:service", exp=-100)
    resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 5, "method": "ping"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_reverts_to_local_token_when_oauth_off(monkeypatch, client):
    monkeypatch.setattr(settings, "oauth_issuer", "")
    monkeypatch.setattr(settings, "mcp_http_token", "legacy")
    denied = client.post("/mcp", json={"jsonrpc": "2.0", "id": 6, "method": "ping"})
    assert denied.status_code == 401
    ok = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 7, "method": "ping"},
        headers={"Authorization": "Bearer legacy"},
    )
    assert ok.status_code == 200