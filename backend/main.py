import asyncio
import hmac
import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .aws_events import EventPublisher
from .brief import build_daily_summary
from .calendar_mcp import build_calendar_client
from .captions import child_captions, why_text
from .captions import ui_strings as caption_ui
from .config import settings
from .db import Database
from .escalation import EscalationManager
from .llm import build_llm, resolve_model_name
from .mcp_server import MCPServer
from .metrics import metrics
from .notifier import Notifier
from .oauth import OAuthContext, OAuthVerifier
from .phrasebook import lookup as phrasebook_lookup
from .phrasebook import pairs as phrasebook_pairs
from .policy import policy_ref
from .ring_simulator import DEFAULT_DEMO_SECRET, SCENARIOS as RING_SCENARIOS
from .ring_simulator import build_payload, serialize_payload, sign_payload
from .triage import EnrichmentPipeline, Tier1Rules
from .util import RateLimiter, client_ip
from .webhook import (
    RingWebhookHandler,
    WebhookError,
    extract_visitor_statement,
    parse_ring_payload,
    request_hash,
    verify_ring_signature,
)

logger = logging.getLogger("accessbell")

db = Database(settings.db_url)
tier1 = Tier1Rules()
_quiet_hours = (
    (settings.quiet_hours_start, settings.quiet_hours_end)
    if settings.quiet_hours_start and settings.quiet_hours_end
    else None
)
pipeline = EnrichmentPipeline(
    db,
    build_llm(settings),
    calendar=build_calendar_client(settings),
    metrics=metrics,
    context_budget_ms=settings.context_budget_ms,
    quiet_hours=_quiet_hours,
)
webhook_handler = RingWebhookHandler(db, debounce_seconds=settings.debounce_seconds)
notifier = Notifier(settings)
rate_limiter = RateLimiter(settings.rate_limit_per_minute)
event_publisher = EventPublisher(settings)


class StreamBroker:
    def __init__(self):
        self._subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue):
        self._subscribers.discard(queue)

    def publish(self, message: dict):
        payload = "data: " + json.dumps(message, ensure_ascii=False) + "\n\n"
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(payload)
                except asyncio.QueueFull:
                    pass

    def close(self):
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(None)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                    queue.put_nowait(None)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass
        self._subscribers.clear()


broker = StreamBroker()
escalation = EscalationManager(db, broker, notifier)
mcp_server = MCPServer(db, settings, escalation, notifier=notifier)
REPLY_ACTIONS = {"leave_at_door", "coming", "not_now", "waiting_for_parent"}


async def _purge_loop():
    interval = max(settings.purge_interval_s, 60)
    while True:
        await asyncio.sleep(interval)
        try:
            purged = await asyncio.to_thread(db.purge_older_than, settings.event_ttl_days)
            if purged:
                logger.info("purged %s stale event(s)", purged)
        except Exception:
            logger.exception("purge loop failed")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.app_env in {"production", "prod"}:
        if settings.api_auth_disabled or not settings.api_token:
            raise RuntimeError("API_TOKEN required and API_AUTH_DISABLED must be false in production")
        if settings.ring_webhook_enabled and not settings.ring_secret:
            raise RuntimeError("RING_WEBHOOK_SECRET required when RING_WEBHOOK_ENABLED in production")
        oauth = OAuthVerifier(settings)
        if not oauth.enabled and not settings.mcp_http_token:
            raise RuntimeError("MCP authentication required in production (configure OAuth or MCP_HTTP_TOKEN)")
    db.init_schema()
    purged = db.purge_older_than(settings.event_ttl_days)
    logger.info("db ready; purged %s event(s) older than %s days", purged, settings.event_ttl_days)
    await escalation.recover()
    purge_task = asyncio.create_task(_purge_loop())
    yield
    purge_task.cancel()
    broker.close()
    escalation.shutdown()
    db.close()


app = FastAPI(title="AccessBell", version="0.1.0", lifespan=lifespan)


def _api_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    query_token = request.query_params.get("token")
    if query_token:
        return query_token
    return request.cookies.get("accessbell_token", "")


@app.middleware("http")
async def _api_auth(request: Request, call_next):
    if settings.api_auth_disabled or not settings.api_token:
        return await call_next(request)
    if not request.url.path.startswith("/api/"):
        return await call_next(request)
    if hmac.compare_digest(_api_token(request), settings.api_token):
        return await call_next(request)
    return JSONResponse(status_code=401, content={"detail": "unauthorized"})

if Path(settings.web_dir).exists():
    app.mount("/assets", StaticFiles(directory=settings.web_dir), name="assets")

snapshots_dir = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "snapshots"
if snapshots_dir.exists():
    app.mount("/static/test_snapshots", StaticFiles(directory=str(snapshots_dir)), name="test_snapshots")


def _bearer_ok(request: Request, expected: str) -> bool:
    if not expected:
        return True
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else auth
    return hmac.compare_digest(token, expected)


def _oauth_challenge(request: Request) -> dict:
    if not settings.mcp_401_www_authenticate:
        return {}
    metadata = str(request.base_url).rstrip("/") + "/.well-known/oauth-protected-resource"
    return {"WWW-Authenticate": f'Bearer resource_metadata="{metadata}"'}


def _rate_limited(request: Request):
    host = request.client.host if request.client else "unknown"
    key = client_ip(host, request.headers.get("x-forwarded-for"), settings.forwarded_allow_ips)
    if not rate_limiter.allow(key):
        raise HTTPException(status_code=429, detail="rate limit exceeded")


def _label_from_evidence(evidence: list, prefix: str) -> str:
    for item in evidence or []:
        if isinstance(item, str) and item.startswith(prefix):
            return item.split(":", 1)[1]
    return ""


def _why_for(triage: dict) -> dict:
    evidence = triage.get("evidence") or []
    grounding = triage.get("grounding") or "generic"
    context_status = triage.get("context_status") or "disabled"
    expected_label = _label_from_evidence(evidence, "expected_context:")
    calendar_label = _label_from_evidence(evidence, "calendar:")
    return {
        language: why_text(
            grounding=grounding,
            evidence=evidence,
            expected_label=expected_label,
            calendar_label=calendar_label,
            context_status=context_status,
            language=language,
            verification_status=triage.get("verification_status") or "no_claim",
        )
        for language in ("en", "vi")
    }


def _share_message(summary: dict) -> str:
    return "AccessBell daily brief (" + summary["date"] + "):\n" + "\n".join(
        f"- {bullet}" for bullet in summary["bullets"]
    )


def _door_log_text(language: str, limit: int) -> str:
    labels = caption_ui(language)
    rows = db.list_events(limit=limit)
    lines = [labels["export_log_title"], labels["export_log_note"], ""]
    for row in reversed(rows):
        triage = json.loads(row.get("triage_json") or "{}") or {}
        caption = triage.get(f"caption_{language}") or triage.get("caption_en") or ""
        evidence = [str(item) for item in triage.get("evidence") or []]
        challenge = triage.get(f"challenge_question_{language}") or triage.get("challenge_question_en") or ""
        urgency = labels["urgency"].format(value=triage.get("urgency", 0))
        verification = labels.get(f"verification_{triage.get('verification_status') or 'no_claim'}", "")
        risk = labels.get(f"risk_{triage.get('risk_level') or 'low'}", "")
        category = triage.get("category") or row.get("kind") or ""
        lines.append(f"{row.get('occurred_at', '')} | {category} | {urgency} | {verification} | {risk}")
        if caption:
            lines.append(f"    {caption}")
        if evidence:
            lines.append(f"    {labels['evidence']}: {', '.join(evidence)}")
        if challenge:
            lines.append(f"    {labels['export_challenge']}: {challenge}")
        lines.append("")
    ref = policy_ref()
    lines.append(labels["export_policy"].format(value=f"{ref['version']} ({ref['short']})"))
    return "\n".join(lines) + "\n"


def _find_event(event_id: str | int):
    try:
        eid = int(event_id)
        ev = db.get_event(eid)
        if ev:
            return ev
    except (ValueError, TypeError):
        pass
    h = request_hash(str(event_id))
    if h:
        ev = db.get_event_by_hash(h)
        if ev:
            return ev
    for row in db.list_events(limit=50):
        raw = json.loads(row.get("raw_json") or "{}")
        data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
        if (
            raw.get("event_id") == str(event_id)
            or data.get("id") == str(event_id)
            or str(row.get("id")) == str(event_id)
        ):
            return db.get_event(row["id"])
    return None


def _serialize(event: dict) -> dict:
    event = dict(event)
    event["raw"] = json.loads(event.pop("raw_json") or "{}")
    triage = json.loads(event.pop("triage_json") or "{}")
    event["triage"] = triage
    event["classification"] = {"label": triage.get("category", "UNKNOWN"), "urgency": triage.get("urgency", 0)}
    event["why"] = _why_for(triage)
    event["caption_child"] = child_captions(triage.get("category") or "") or {}
    event["visitor_statement"] = extract_visitor_statement(event["raw"])
    event["door_turns"] = db.list_door_turns(event["id"])
    return event


def _insert_from_payload(payload: dict, source: str) -> dict:
    if source == "mock":
        payload = dict(payload)
        meta = dict(payload.get("meta") or {})
        meta["request_id"] = f"mock-{uuid4().hex}"
        payload["meta"] = meta
    parsed = parse_ring_payload(payload)
    event_id = db.insert_event(
        source,
        parsed["device_id"],
        parsed["kind"],
        parsed["occurred_at"],
        payload,
    )
    return db.get_event(event_id)


async def _run_enrichment(event: dict):
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(pipeline.enrich, event),
            timeout=max(settings.enrich_budget_ms, 1) / 1000.0,
        )
    except TimeoutError:
        return tier1.classify(event["kind"]), False


async def _enrich_async(event_id: int):
    started = time.perf_counter()
    event = db.get_event(event_id)
    if event is None:
        return
    result, ok = await _run_enrichment(event)
    status = "enriched" if ok else "enrichment_failed"
    db.update_triage(event_id, result.model_dump(), status=status)
    stored = db.get_event(event_id)
    triage = json.loads(stored.get("triage_json") or "{}")
    raw = json.loads(stored.get("raw_json") or "{}") if isinstance(stored.get("raw_json"), str) else (stored.get("raw_json") or {})
    client_event_id = raw.get("event_id") or ""
    visitor_statement = extract_visitor_statement(raw)
    urgency_raw = triage.get("urgency", 0)
    urgency_scaled = 3 if urgency_raw >= 7 else (2 if urgency_raw >= 5 else (1 if urgency_raw >= 2 else 0))
    color = "red" if urgency_scaled >= 3 else ("amber" if urgency_scaled >= 2 else "green")
    broker.publish(
        {
            "type": "alert_enriched",
            "alert_type": "tier2_enriched",
            "event_id": client_event_id or event_id,
            "internal_event_id": event_id,
            "status": status,
            "triage": triage,
            "label": triage.get("category", "UNKNOWN"),
            "category": triage.get("category", "UNKNOWN"),
            "urgency": urgency_scaled,
            "urgency_10": urgency_raw,
            "message": triage.get("caption_en", ""),
            "color": color,
            "why": _why_for(triage),
            "caption_child": child_captions(triage.get("category") or "") or {},
            "visitor_statement": visitor_statement,
        }
    )
    escalation.schedule(event_id, triage)
    event_publisher.publish(stored, triage)
    metrics.observe("enrich_ms", (time.perf_counter() - started) * 1000.0)


async def _announce(event: dict, started: float | None = None):
    started = started if started is not None else time.perf_counter()
    raw_payload = json.loads(event.get("raw_json") or "{}") if isinstance(event.get("raw_json"), str) else (event.get("raw_json") or {})
    client_event_id = raw_payload.get("event_id") or ""
    visitor_statement = extract_visitor_statement(raw_payload)
    raw = tier1.classify(event["kind"])
    latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
    broker.publish(
        {
            "type": "alert_raw",
            "alert_type": "tier1_raw",
            "event_id": client_event_id or event["id"],
            "internal_event_id": event["id"],
            "text": raw.caption_en,
            "text_en": raw.caption_en,
            "text_vi": raw.caption_vi,
            "category": raw.category.value,
            "label": raw.category.value,
            "urgency": 0,
            "message": raw.caption_en,
            "color": "white",
            "latency_ms": latency_ms,
            "visitor_statement": visitor_statement,
        }
    )
    metrics.observe("tier1_ms", latency_ms)
    asyncio.create_task(_enrich_async(event["id"]))


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "mock_mode": settings.mock_mode,
        "llm_provider": settings.llm_provider,
        "llm_model": resolve_model_name(settings) or "stub",
    }


@app.get("/api/policy")
async def get_policy():
    return policy_ref()


@app.get("/api/metrics")
async def get_metrics():
    events = await asyncio.to_thread(db.list_events, limit=5000)
    grounding = {"grounded": 0, "generic": 0, "demoted_insufficient_evidence": 0}
    for event in events:
        try:
            triage = json.loads(event.get("triage_json") or "{}")
        except (TypeError, ValueError):
            triage = {}
        status = triage.get("grounding")
        if status in grounding:
            grounding[status] += 1
    total = len(events)
    latency = metrics.snapshot()
    return {
        "source": "fixture-derived, not production telemetry",
        "events_total": total,
        "event_status": db.event_status_counts(),
        "grounding": grounding,
        "demoted_ratio": round(grounding["demoted_insufficient_evidence"] / total, 3) if total else 0.0,
        "escalation_status": db.escalation_status_counts(),
        "timers": latency["timers"],
        "latency_counters": latency["counters"],
        "policy": policy_ref(),
    }


@app.get("/")
async def index():
    index_path = Path(settings.web_dir) / "index.html"
    if not index_path.exists():
        return {"service": "AccessBell", "ui": "not built", "web_dir": settings.web_dir}
    return FileResponse(index_path)


@app.get("/api/stream")
@app.get("/api/events/stream")
async def stream(request: Request):
    queue = broker.subscribe()

    async def generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if item is None:
                    break
                yield item
        finally:
            broker.unsubscribe(queue)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.post("/webhooks/ring")
@app.post("/webhook/ring")
async def ring_webhook(request: Request):
    started = time.perf_counter()
    _rate_limited(request)
    body = await request.body()
    signature = ""
    for header_name in (settings.ring_signature_header, "X-Signature", "X-Ring-Signature"):
        signature = request.headers.get(header_name, "")
        if signature:
            break
    if settings.ring_webhook_enabled or settings.ring_secret:
        if not settings.ring_secret:
            raise HTTPException(status_code=500, detail="RING_WEBHOOK_SECRET not configured")
        if not verify_ring_signature(body, signature, settings.ring_secret):
            raise HTTPException(status_code=401, detail="invalid signature")
    try:
        event, deduped = webhook_handler.handle(body)
    except WebhookError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deduped:
        await _announce(event, started)
    metrics.observe("webhook_to_sse_ms", (time.perf_counter() - started) * 1000.0)
    return {"ok": True, "event_id": event["id"], "deduped": deduped}


@app.post("/api/simulate")
async def simulate(request: Request, fixture: str = "doorbell_unknown"):
    if not settings.mock_mode:
        raise HTTPException(status_code=404, detail="simulation endpoint disabled when mock_mode is false")
    if not _bearer_ok(request, settings.demo_token):
        raise HTTPException(status_code=401, detail="unauthorized")
    _rate_limited(request)
    path = Path(settings.mock_events_dir) / f"{fixture}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"fixture not found: {fixture}")
    started = time.perf_counter()
    payload = json.loads(path.read_text(encoding="utf-8"))
    event = _insert_from_payload(payload, "mock")
    await _announce(event, started)
    metrics.observe("webhook_to_sse_ms", (time.perf_counter() - started) * 1000.0)
    return {"ok": True, "event_id": event["id"], "category": tier1.classify(event["kind"]).category.value}


DEMO_MCP_TOOLS = {
    "get_door_alerts",
    "get_event_detail",
    "get_context_snapshot",
    "get_daily_summary",
    "list_expected_context",
    "confirm_event",
    "send_quick_reply",
}


@app.post("/api/demo/mcp")
async def demo_mcp(request: Request):
    """Mock-mode bridge to the MCP server for the in-app Alexa+ client.

    The browser never holds the MCP token, so the demo client falls back to this
    route when /mcp rejects the call. Same MCP server, same tools, same JSON-RPC.
    """
    if not settings.mock_mode:
        raise HTTPException(status_code=404, detail="demo endpoint disabled when mock_mode is false")
    _rate_limited(request)
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid JSON") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="expected a JSON object")
    if body.get("method") == "tools/call":
        name = ((body.get("params") or {}).get("name")) or ""
        if name not in DEMO_MCP_TOOLS:
            raise HTTPException(status_code=403, detail=f"tool not available in demo mode: {name}")
    started = time.perf_counter()
    response = mcp_server.handle(body)
    metrics.observe("mcp_tool_ms", (time.perf_counter() - started) * 1000.0)
    if response is None:
        return Response(status_code=202)
    return response


class RingSimIn(BaseModel):
    scenario: str = "police_claim"
    visitor_statement: str | None = None
    device_id: str = "ring_doorbell_01"


@app.get("/api/simulate/ring/scenarios")
async def ring_scenarios():
    if not settings.mock_mode:
        raise HTTPException(status_code=404, detail="simulation endpoint disabled when mock_mode is false")
    return {
        "scenarios": [
            {"key": key, "kind": spec["kind"], "statement": spec["statement"]}
            for key, spec in RING_SCENARIOS.items()
        ]
    }


@app.post("/api/simulate/ring")
async def simulate_ring(request: Request, payload: RingSimIn | None = None):
    if not settings.mock_mode:
        raise HTTPException(status_code=404, detail="simulation endpoint disabled when mock_mode is false")
    if not _bearer_ok(request, settings.demo_token):
        raise HTTPException(status_code=401, detail="unauthorized")
    _rate_limited(request)
    body_in = payload or RingSimIn()
    if body_in.scenario not in RING_SCENARIOS:
        raise HTTPException(status_code=400, detail=f"unknown Ring scenario: {body_in.scenario}")
    started = time.perf_counter()
    envelope = build_payload(
        body_in.scenario,
        visitor_statement=body_in.visitor_statement,
        device_id=body_in.device_id,
    )
    body = serialize_payload(envelope)
    secret = settings.ring_secret or DEFAULT_DEMO_SECRET
    signature = sign_payload(body, secret)
    signature_valid = verify_ring_signature(body, signature, secret)
    if not signature_valid:
        raise HTTPException(status_code=500, detail="Ring simulator signature self-check failed")
    try:
        event, deduped = webhook_handler.handle(body, debounce=False)
    except WebhookError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deduped:
        await _announce(event, started)
    metrics.observe("webhook_to_sse_ms", (time.perf_counter() - started) * 1000.0)
    statement = extract_visitor_statement(envelope)
    return {
        "ok": True,
        "event_id": event["id"],
        "ring_event_id": envelope["data"]["id"],
        "scenario": body_in.scenario,
        "version": envelope["meta"]["version"],
        "signature_valid": signature_valid,
        "visitor_statement": statement,
        "deduped": deduped,
    }


@app.get("/api/events")
async def list_events(since: str | None = None, until: str | None = None, limit: int = 50):
    rows = await asyncio.to_thread(db.list_events, since=since, until=until, limit=max(1, min(limit, 500)))
    return {"events": [_serialize(e) for e in rows]}


@app.get("/api/events/{event_id}")
async def get_event(event_id: str):
    event = _find_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="unknown event")
    return _serialize(event)


class ReplyIn(BaseModel):
    action: str | None = None
    template: str | None = None
    source: str = "pwa"


@app.post("/api/events/{event_id}/quick-reply")
@app.post("/api/events/{event_id}/reply")
async def quick_reply(event_id: str, payload: ReplyIn):
    action = payload.action or payload.template or "leave_at_door"
    if action == "please_leave_at_door":
        action = "leave_at_door"
    if action not in REPLY_ACTIONS:
        raise HTTPException(status_code=400, detail=f"invalid action: {action}")
    event = _find_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="unknown event")
    db.add_label(event["id"], f"device:{event['device_id']}", action, payload.source)
    escalation.acknowledge(event["id"], payload.source)
    triage = json.loads(event.get("triage_json") or "{}")
    return {"ok": True, "dispatched": notifier.announce(event, triage)}


class ConfirmIn(BaseModel):
    label: str
    source: str = "alexa"


@app.post("/api/events/{event_id}/confirm")
async def confirm_event(event_id: int, payload: ConfirmIn):
    event = db.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="unknown event")
    if not payload.label.strip():
        raise HTTPException(status_code=400, detail="label required")
    db.add_label(event_id, f"device:{event['device_id']}", payload.label, payload.source)
    escalation.acknowledge(event_id, payload.source)
    return {"ok": True}


class DoorTalkIn(BaseModel):
    speaker: str
    text: str
    lang: str = "en"


@app.post("/api/events/{event_id}/door-talk")
async def add_door_talk(event_id: str, payload: DoorTalkIn):
    event = _find_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="unknown event")
    try:
        turn_id = db.add_door_turn(event["id"], payload.speaker, payload.text, payload.lang)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    turn = next((t for t in db.list_door_turns(event["id"]) if t["id"] == turn_id), None)
    # Phrasebook only: exact fixed-prompt match, else null (never fake
    # a free-text translation). Translation preview in the UI does not
    # store a turn — it uses the same fixed prompts client-side.
    return {"ok": True, "turn_id": turn_id, "turn": turn, "phrasebook": phrasebook_lookup(payload.text)}


@app.get("/api/events/{event_id}/door-talk")
async def list_door_talk(event_id: str):
    event = _find_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="unknown event")
    return {"turns": db.list_door_turns(event["id"])}


class ExpectedIn(BaseModel):
    kind: str
    label: str
    window_start: str
    window_end: str
    source: str = "alexa"


@app.post("/api/expected")
async def add_expected(payload: ExpectedIn):
    expected_id = db.add_expected_context(
        payload.kind, payload.label, payload.window_start, payload.window_end, payload.source
    )
    return {"ok": True, "id": expected_id}


@app.get("/api/expected")
async def list_expected(limit: int = 100):
    return {"windows": db.list_expected_context(max(1, min(limit, 200)))}


@app.delete("/api/expected/{expected_id}")
async def delete_expected(expected_id: int):
    if not db.clear_expected_context(expected_id):
        raise HTTPException(status_code=404, detail="expected window not found")
    return {"ok": True, "removed": expected_id}


@app.get("/api/brief")
async def brief(date: str | None = None, lang: str | None = None):
    language = lang or db.get_prefs().get("language") or "en"
    return build_daily_summary(db, date, language)


@app.get("/api/door-log.txt")
async def door_log_txt(lang: str | None = None, limit: int = 100):
    language = lang or db.get_prefs().get("language") or "en"
    return Response(
        content=_door_log_text(language, max(1, min(limit, 500))),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="accessbell-door-log.txt"'},
    )


class ShareIn(BaseModel):
    consent: bool
    recipient: str
    date: str | None = None


@app.post("/api/share/preview")
async def share_preview(payload: ShareIn):
    if not payload.recipient.strip():
        raise HTTPException(status_code=400, detail="recipient required")
    language = db.get_prefs().get("language") or "en"
    summary = build_daily_summary(db, payload.date, language)
    return {
        "ok": True,
        "recipient": payload.recipient,
        "message": _share_message(summary),
        "requires_consent": True,
    }


@app.post("/api/share")
async def share(payload: ShareIn):
    if not payload.consent:
        raise HTTPException(status_code=400, detail="explicit consent required to share")
    if not payload.recipient.strip():
        raise HTTPException(status_code=400, detail="recipient required")
    language = db.get_prefs().get("language") or "en"
    summary = build_daily_summary(db, payload.date, language)
    message = _share_message(summary)
    share_id = db.log_share(summary["date"], payload.recipient, message)
    sms_status = notifier.sms(payload.recipient, message)
    return {"ok": True, "share_id": share_id, "message": message, "sms": sms_status}


@app.get("/api/share/log")
async def share_log(limit: int = 50):
    rows = db.list_shares(max(1, min(limit, 200)))
    return {"log": [dict(row, read_back=True) for row in rows]}


@app.post("/api/share/{share_id}/revoke")
async def revoke_share(share_id: int):
    original = db.get_share(share_id)
    if original is None:
        raise HTTPException(status_code=404, detail="share not found")
    audit_id = db.log_share(
        original["brief_date"], original["recipient"], f"revoked share #{share_id}"
    )
    return {"ok": True, "revoked": share_id, "audit_id": audit_id}


class PrefsIn(BaseModel):
    mode: str = "both"
    language: str = "en"


@app.get("/api/prefs")
async def get_prefs():
    return db.get_prefs()


class EscalationContactIn(BaseModel):
    label: str
    recipient: str
    channel: str = "sms"


@app.post("/api/escalation/contacts")
async def add_escalation_contact(payload: EscalationContactIn):
    if not payload.label.strip() or not payload.recipient.strip():
        raise HTTPException(status_code=400, detail="label and recipient required")
    contact_id = db.add_escalation_contact(payload.label, payload.recipient, payload.channel)
    return {"ok": True, "id": contact_id}


@app.get("/api/escalation/contacts")
async def list_escalation_contacts():
    return {"contacts": db.list_escalation_contacts(enabled_only=False)}


@app.delete("/api/escalation/contacts/{contact_id}")
async def revoke_escalation_contact(contact_id: int):
    if not db.revoke_escalation_contact(contact_id):
        raise HTTPException(status_code=404, detail="contact not found or already revoked")
    return {"ok": True, "revoked": contact_id}


class EscalationPolicyIn(BaseModel):
    enabled: bool | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    min_urgency: int | None = Field(default=None, ge=0, le=10)


@app.get("/api/escalation/policy")
async def get_escalation_policy():
    return db.get_escalation_policy()


@app.post("/api/escalation/policy")
async def set_escalation_policy(payload: EscalationPolicyIn):
    return db.set_escalation_policy(payload.enabled, payload.timeout_seconds, payload.min_urgency)


@app.get("/api/escalation/log")
async def list_escalation_log(limit: int = 50):
    return {"log": db.list_escalation_log(max(1, min(limit, 200)))}


class StopIn(BaseModel):
    event_id: int
    source: str = "pwa"


@app.post("/api/escalation/stop")
async def stop_escalation(payload: StopIn):
    if db.get_event(payload.event_id) is None:
        raise HTTPException(status_code=404, detail="unknown event")
    stopped = escalation.acknowledge(payload.event_id, payload.source)
    broker.publish({"type": "escalation_stopped", "event_id": payload.event_id})
    return {"ok": True, "stopped": stopped}


@app.post("/api/prefs")
async def set_prefs(payload: PrefsIn):
    if payload.mode not in {"caption", "voice", "both"}:
        raise HTTPException(status_code=400, detail="mode must be caption|voice|both")
    db.set_prefs(payload.mode, payload.language)
    return {"ok": True}


@app.get("/api/ui-strings")
async def ui_strings_endpoint(lang: str | None = None):
    language = lang or db.get_prefs().get("language") or "en"
    if language not in ("en", "vi"):
        language = "en"
    return {"language": language, "strings": caption_ui(language), "phrasebook": phrasebook_pairs()}


@app.get("/api/advise")
async def advise(limit: int = 200):
    events = await asyncio.to_thread(db.list_events, limit=max(1, min(limit, 1000)))
    demoted_total = 0
    urgent_unanswered = 0
    groups: dict[tuple, int] = {}
    for event in events:
        try:
            triage = json.loads(event.get("triage_json") or "{}")
        except (TypeError, ValueError):
            triage = {}
        if triage.get("grounding") == "demoted_insufficient_evidence":
            demoted_total += 1
            hour = (event.get("occurred_at") or "")[11:13]
            if hour:
                key = (event.get("device_id") or "unknown", hour)
                groups[key] = groups.get(key, 0) + 1
        if (triage.get("urgency") or 0) >= 7 and not db.labels_for_event(event["id"]):
            urgent_unanswered += 1
    suggestions = []
    for (device_id, hour), count in sorted(groups.items(), key=lambda item: -item[1]):
        if count >= 2:
            suggestions.append(
                {
                    "kind": "expected_window",
                    "device_id": device_id,
                    "reason": f"{count} generic alerts around {hour}:00",
                    "auto_write": False,
                }
            )
        if len(suggestions) >= 5:
            break
    if urgent_unanswered:
        suggestions.append(
            {
                "kind": "review_urgent",
                "reason": f"{urgent_unanswered} high-urgency alerts without a reply",
                "auto_write": False,
            }
        )
    return {
        "read_only": True,
        "auto_write": False,
        "demoted_total": demoted_total,
        "urgent_unanswered": urgent_unanswered,
        "suggestions": suggestions,
    }


@app.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource():
    return OAuthVerifier(settings).protected_resource_metadata()


@app.post("/mcp")
async def mcp(request: Request):
    oauth = OAuthVerifier(settings)
    if oauth.enabled:
        context = oauth.authenticate(
            request.headers.get("authorization", ""),
            request.headers.get("cf-access-jwt-assertion", ""),
        )
        if context is None:
            if settings.mcp_http_token and _bearer_ok(request, settings.mcp_http_token):
                context = OAuthContext(scope="user")
            else:
                raise HTTPException(
                    status_code=401, detail="oauth: missing or invalid token", headers=_oauth_challenge(request)
                )
        try:
            body = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="invalid JSON") from exc
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="expected a JSON object")
        if not context.can_act_for_user and body.get("method") == "tools/call":
            raise HTTPException(status_code=403, detail="service token cannot act for a user")
    else:
        if not _bearer_ok(request, settings.mcp_http_token):
            raise HTTPException(status_code=401, detail="unauthorized", headers=_oauth_challenge(request))
        try:
            body = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="invalid JSON") from exc
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="expected a JSON object")
    if settings.mcp_origin:
        origin = (request.headers.get("origin") or "").strip()
        if origin:
            allowed = {urlparse(entry).netloc or entry.strip() for entry in settings.mcp_origin.split(",") if entry.strip()}
            if urlparse(origin).netloc not in allowed and origin not in allowed:
                raise HTTPException(status_code=403, detail="origin not allowed")
    started = time.perf_counter()
    response = mcp_server.handle(body)
    metrics.observe("mcp_tool_ms", (time.perf_counter() - started) * 1000.0)
    if response is None:
        return Response(status_code=202)
    return response


_ring_client = None


def _get_ring_client():
    global _ring_client
    if _ring_client is None:
        from .ring_client import RingClient

        _ring_client = RingClient(settings.ring_account_token, base_url=settings.ring_api_base_url)
    return _ring_client


@app.get("/api/ring/devices")
async def ring_devices():
    if not settings.ring_account_token:
        raise HTTPException(status_code=501, detail="RING_ACCOUNT_TOKEN not configured; mock mode uses fixtures")
    try:
        return await asyncio.to_thread(_get_ring_client().devices)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc