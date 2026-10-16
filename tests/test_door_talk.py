"""Door-talk tests: stored turns, validation, phrasebook-only translation."""

import os
import uuid

if "DB_URL" not in os.environ:
    os.environ["DB_URL"] = f"sqlite:////tmp/accessbell_talk_{uuid.uuid4().hex}.db"
os.environ["LLM_PROVIDER"] = "stub"
os.environ["RATE_LIMIT_PER_MINUTE"] = "1000"
os.environ["DEMO_TOKEN"] = ""

import pytest
from fastapi.testclient import TestClient

from backend import main as main_module
from backend.phrasebook import lookup

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture(scope="module")
def client():
    with TestClient(main_module.app) as test_client:
        yield test_client


def _make_event(client):
    resp = client.post("/api/simulate?fixture=doorbell_unknown")
    assert resp.status_code == 200
    return resp.json()["event_id"]


def test_phrasebook_exact_match_both_directions():
    assert lookup("Who are you?") == {"text": "Bạn là ai?", "lang": "vi"}
    assert lookup("  bạn là ai? ") == {"text": "Who are you?", "lang": "en"}
    assert lookup("WHAT IS YOUR ORDER NUMBER?") == {"text": "Mã đơn hàng của bạn là gì?", "lang": "vi"}


def test_phrasebook_rejects_free_text():
    assert lookup("Hello, how is the weather today?") is None
    assert lookup("") is None
    assert lookup("Who are you really?") is None


def test_door_talk_stores_and_lists_turns(client):
    event_id = _make_event(client)
    resp = client.post(
        f"/api/events/{event_id}/door-talk",
        json={"speaker": "visitor", "text": "Who are you?", "lang": "en"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["phrasebook"] == {"text": "Bạn là ai?", "lang": "vi"}
    assert body["turn"]["text"] == "Who are you?"
    listed = client.get(f"/api/events/{event_id}/door-talk").json()["turns"]
    assert [t["text"] for t in listed] == ["Who are you?"]
    event = client.get(f"/api/events/{event_id}").json()
    assert event["door_turns"] == listed


def test_door_talk_free_text_has_null_phrasebook(client):
    event_id = _make_event(client)
    resp = client.post(
        f"/api/events/{event_id}/door-talk",
        json={"speaker": "resident", "text": "Hello there, nice day today", "lang": "en"},
    )
    assert resp.status_code == 200
    assert resp.json()["phrasebook"] is None


def test_door_talk_rejects_bad_speaker_lang_empty(client):
    event_id = _make_event(client)
    assert client.post(
        f"/api/events/{event_id}/door-talk",
        json={"speaker": "dog", "text": "Woof", "lang": "en"},
    ).status_code == 400
    assert client.post(
        f"/api/events/{event_id}/door-talk",
        json={"speaker": "visitor", "text": "Hi", "lang": "fr"},
    ).status_code == 400
    assert client.post(
        f"/api/events/{event_id}/door-talk",
        json={"speaker": "visitor", "text": "   ", "lang": "en"},
    ).status_code == 400


def test_door_talk_unknown_event_404(client):
    assert client.post(
        "/api/events/999999/door-talk",
        json={"speaker": "visitor", "text": "Hi", "lang": "en"},
    ).status_code == 404
    assert client.get("/api/events/999999/door-talk").status_code == 404
