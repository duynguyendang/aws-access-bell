# AccessBell

> **Multi-sensory AI door intelligence for accessibility and independent living.**  
> Ring · Fire TV · Alexa+ (MCP) · AWS Bedrock

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Most doorbell apps are built around a phone chime and a small screen.** That works well for many
people — and leaves others out, often without anyone intending it.

AccessBell is a **companion layer** on Ring, Fire TV, and Alexa+: the same door event, delivered in
ways more people in the household can actually use. It is not a new camera, and it is not a
caregiver surveillance product. The person who lives there stays in control.

| | |
|---|---|
| **See** | Full-screen caption on Fire TV in &lt;200 ms (rules first — no waiting on a model) |
| **Understand** | Plain-language *why* in EN/VI, with confidence and evidence — it will not invent who is at the door |
| **Ask** | Spoken daily brief and door history via **Alexa+ MCP** |
| **Act** | One tap, TV remote (D-pad), or voice |
| **Protect** | **Optional** escalation if nobody answers — audited, revocable, off by default |

**Tagline:** *Accessibility, not surveillance.*

| Situation people describe | How AccessBell can help |
|---|---|
| Hard of hearing — the hallway strobe is easy to miss from the kitchen | Large, high-contrast **Fire TV caption**; urgency shown as **text**, not color alone |
| Blind or low vision — hard to “scan” a timeline of thumbnails | Spoken brief and TTS-friendly captions; history answered with event citations |
| Limited mobility — the phone is across the room, or gestures are tiring | Reply from the **TV remote** or by voice; no swipes, no hurry |
| Living alone — a missed pharmacy drop can turn into a long worry | Expected windows + **optional** escalation to someone you choose, always audited |
| Child home after school — unsure who is at the door; parent at work | Calm, simple caption and large TV buttons; parent is contacted **only** when you allow it and nobody answers |
| Multi-generational home — one doorbell, different needs | The same event: caption for a grandparent, buttons for a child, a parent loop if wanted |
| Many “eldercare” tools put monitoring first | Here the **resident is the user**; sharing is opt-in, logged, and easy to revoke |

**In one sentence:** AccessBell makes the front door understandable on the screens and speakers a
household already has — without turning the home into a surveillance product.

---

## Architecture at a glance

AccessBell is the **door-intelligence layer** in a **multi-MCP home** — not a monolith calendar app
and not a new camera.

```
                    ┌──────────────────┐
   schedule intent  │  Calendar MCP    │  (household schedule — any compliant server)
        │           └────────▲─────────┘
        │    Alexa+ orchestrates tools by intent
        ▼                    │
┌───────────────┐    ┌───────┴────────┐    ┌─────────────────────┐
│  Voice / app  │◄──►│    Alexa+      │◄──►│  AccessBell MCP     │
│  (resident)   │    │  (MCP client)  │    │  door intelligence  │
└───────────────┘    └────────────────┘    └──────────▲──────────┘
                                                      │
                     Ring device signals              │
                     webhook + HMAC                   │
┌───────────────┐    Partner API v1.1                 │
│ Ring cloud    │─────────────────────────────────────┤
└───────────────┘                                     │
                           Fire TV / PWA  ◄───────────┤
                           captions + D-pad           │
                           consent SMS/share ◄────────┘
```

| Piece | Role |
|---|---|
| **Ring** | Emits door/motion events (webhook). Physical device not required to develop. |
| **AccessBell** | Ingest → Tier 1 fast caption → Tier 2 grounded meaning → act / escalate / brief |
| **AccessBell MCP** | Door tools for agents (alerts, brief, expected context, replies, escalation, a11y prefs) |
| **Calendar MCP** | Holds personal/household schedule — **separate** from AccessBell |
| **Alexa+** | Orchestrator: can call calendar tools **and** AccessBell tools in one turn |
| **Fire TV / PWA** | Largest-screen captions and one-tap / remote replies |

**How schedule joins the door**

| Pattern | What happens |
|---|---|
| **Orchestrator join (primary)** | *“Expect pharmacy ~10”* → Alexa writes calendar (if connected) **and** `add_expected_context` on AccessBell |
| **Pipeline join (optional)** | AccessBell may call a Calendar MCP `list_events` during enrichment — **off by default** |

*Honest bound:* the Alexa+ MCP toolkit does not give a single add-on your Google/Outlook calendar.
AccessBell stores **door intent** you (or the orchestrator) explicitly provide; it does not scrape
private calendars in MVP.

### Why multi-MCP raises the product

- **Right tool, right job** — schedule stays in calendar systems; door logic stays in AccessBell  
- **Alexa+ has a real role** — voice orchestration across tools, not a thin remote  
- **Evidence gate stays local** — even with calendar context, AccessBell demotes captions that lack evidence  
- **Consent stays local** — escalation/share never leave AccessBell’s audit model  

### Schedule-aware door (product)

Households already plan pharmacy drops, packages, and school runs. When that intent is written into
AccessBell, the next ring can ground to it:

| | |
|---|---|
| **You set intent** | Voice or API: `add_expected_context` (e.g. pharmacy ~10:00) |
| **The door uses it** | In-window events get clearer captions + evidence; routine visits can be quieter |
| **You stay in control** | Opt-in memory; revoke/clear anytime; no face recognition |

---

## How it works

```
Ring webhook (HMAC)  ──►  AccessBell  ──►  Fire TV / PWA  (Tier 1 caption <200ms)
        optional mock              │
                                   ├─►  Tier 2 (rules → Bedrock/stub) + expected_context
                                   ├─►  AccessBell MCP  ◄──►  Alexa+  ◄──►  Calendar MCP
                                   └─►  consent escalation / share (opt-in)
```

1. **Tier 1 (rules)** — instant “Someone is at the door” (never blocked on the model).  
2. **Tier 2 (LLM)** — EN/VI captions with **confidence + evidence**; specific categories without
   evidence are **demoted** in code (grounding rule).  
3. **Surfaces** — Fire TV visual, Alexa+ voice via **AccessBell MCP**, PWA quick replies.  
4. **Schedule** — expected windows (door intent) improve grounding; personal calendars stay in
   other MCP servers if you connect them via Alexa+.  
5. **Protect** — unanswered high-urgency → consented contact; audit trail; revoke works.

---

## Features (MVP)

- Ring webhook ingest with HMAC-SHA256 (`X-Signature: sha256=…`), Partner API **v1.1** payloads,
  `request_id` idempotency + debounce  
- Event taxonomy: `MED_DELIVERY`, `PACKAGE_DELIVERY`, `FAMILY_VISITOR`, `UNKNOWN_VISITOR`, `MOTION_ANOMALY`  
- Evidence-grounded triage: `category`, `confidence`, `evidence[]`, captions **EN + VI** (TTS-safe)  
- Fire TV-friendly web UI: large text, urgency **text + color**, SSE live, D-pad navigation,
  **why-line + grounding badge**, **EN/VI**, **child mode**, escalation **countdown + Stop**, PWA manifest
- **Read-only advisor** (`GET /api/advise`) suggests expected windows — never auto-writes  
- Self-hosted **MCP server** (Streamable HTTP, spec **2025-11-25**) — 11 tools for Alexa+ / agents  
- **Evidence gate made legible**: triage carries `grounding` (`grounded` / `generic` / `demoted_insufficient_evidence`) + a plain-language why-line
- **Door calendar**: `add` / `list` / `clear` expected context; optional **Calendar MCP** join (J2, off by default)
- **Child-safe captions** and **share protocol** (preview → consent → apply → read-back → revoke)  
- Quick replies: leave package / coming / not now, plus child-friendly “waiting for parent”  
- Daily personal brief + **consent-driven share** (audit log)  
- **Consent escalation** (default OFF): *“if nobody answers, tell Lan”* — durable across restarts  
- **Mock mode** — full demo without Ring hardware (`MOCK_MODE=true`)  
- **Bedrock** via LangChain Converse + structured `TriageResult` (AWS Builder mini)  
- SQLite or Postgres; Docker / Cloud Run scripts; **268 tests** (SQLite; Postgres when DSN set)

---

## Repository layout

```
aws-access-bell/
├── README.md
├── LICENSE
├── policy.yaml             # machine-readable privacy/guardrail policy
├── .env.example
├── Dockerfile / docker-compose.yml   # container + local demo stack
├── requirements.txt        # core (stub runs offline) + requirements-llm.txt / requirements-postgres.txt / requirements-dev.txt
├── .github/workflows/ci.yml          # pytest (sqlite + postgres) + docker build + container smoke
├── backend/
│   ├── main.py             # FastAPI app: API routes, SSE stream, MCP endpoint
│   ├── config.py           # env-based Settings (typed)
│   ├── db.py               # repository facade (SQLite/Postgres via storage dialects)
│   ├── storage/            # sqlite.py + postgres.py dialects + make_dialect()
│   ├── schema.sqlite.sql / schema.postgres.sql   # DDL per dialect
│   ├── webhook.py          # Ring Partner API webhook + HMAC-SHA256 + v1.1 parse + debounce
│   ├── ring_client.py      # Ring Partner API client (api.amazonvision.com; optional live)
│   ├── captions.py         # EN/VI presentation strings (single source; TTS-safe)
│   ├── triage.py           # Tier 1 rules + Tier 2 pipeline; pydantic TriageResult
│   ├── escalation.py       # EscalationManager: durable pending + acknowledge/audit
│   ├── brief.py            # Daily personal brief
│   ├── mcp_server.py       # MCP tools over Streamable HTTP (JSON-RPC 2.0)
│   ├── calendar_mcp.py     # optional Calendar MCP client join (J2, off by default)
│   ├── policy.py           # policy.yaml version + SHA (audit / metrics)
│   ├── oauth.py            # OAuth 2.1 resource-server verification (JWKS, scopes, CF header)
│   ├── notifier.py         # Pluggable announce / SMS (no-op in mock)
│   ├── util.py             # RateLimiter, ISO timestamps
│   ── llm/
│       ├── base.py         # TriageLLM protocol
│       ├── stub.py         # deterministic offline provider (no deps)
│       ├── langchain_provider.py  # one ChatModel + with_structured_output(TriageResult) for all live LLMs
│       └── __init__.py     # build_llm(settings) provider factory
├── web/                    # Fire TV + PWA UI (index.html / app.js / style.css, manifest + icon, SSE, D-pad, EN/VI)
├── mock/events/            # 6 fixture stories (Ring Partner API v1.1 envelopes)
├── mock/calendar_mcp/      # optional Calendar MCP stub (J2 demo)
├── prompts/triage.txt      # LLM system prompt: TriageResult contract + guardrails
├── scripts/                # demo_story.py (guided demo), demo_local.py, reset_db.py, ablation_evidence.py, check_docs_consistency.py, deploy_cloudrun.sh, smoke_docker.sh
├── docs/
│   ├── ARCHITECTURE.md     # technical design: flows, API, auth, data model, tests traceability
│   ├── DEPLOYMENT.md       # system shape, deploy targets, scaling, secrets, go-live checklist
│   ── internal/           # strategy + planning notes — local only, not published (gitignored)
└── tests/                  # pytest: triage, captions/a11y, Ring Partner API v1.1 (webhook/hmac/idempotency), db (sqlite+postgres), mcp, api, escalation, oauth, llm factory
```

---

## Quick start

### Prerequisites

- Python 3.11+  
- AWS account with Bedrock model access (or set `LLM_PROVIDER=stub` for offline)  
- Optional: Ring developer credentials, Alexa+ / MCP client  

### Run with mock data (no Ring required)

```bash
git clone <this-repo>
cd aws-access-bell
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env

# Offline demo without Bedrock
export MOCK_MODE=true
export LLM_PROVIDER=stub

python -m uvicorn backend.main:app --reload --port 8080
```

Open:

- API: http://localhost:8080/health  
- UI: http://localhost:8080/  
- Inject demo event: `POST /api/simulate` or run `scripts/demo_local.py`

### No AWS account? Everything still works

| Piece | AWS-typical | No-AWS path (already wired) |
|---|---|---|
| LLM | Bedrock | `LLM_PROVIDER=stub` (offline) or `ollama` (local) or `openai` / `anthropic` / `google` (free-tier keys) |
| MCP auth | Cognito | Leave `OAUTH_ISSUER` empty → `MCP_HTTP_TOKEN` local mode; or Okta Free Developer org (see `.env.example`) |
| Ring | live webhook | `MOCK_MODE=true` fixtures |

Bedrock and Cognito are **optional** production paths. The default is offline-friendly: "designed
for Bedrock, tested with `stub`, flip via env."  

### Environment

See `.env.example` for all variables:

| Variable | Default | Purpose |
|---|---|---|
| `MOCK_MODE` | `true` | Use fixtures instead of live Ring |
| `LLM_PROVIDER` | `stub` | `stub` \| `bedrock` \| `openai` \| `anthropic` \| `google` \| `ollama` |
| `LLM_MODEL` | provider default | Optional model override (per-provider defaults below) |
| `DB_URL` | `sqlite:///accessbell.db` | Storage: SQLite or `postgresql://user:pw@host:5432/db` |
| `DB_PATH` | `accessbell.db` | SQLite file (used when `DB_URL` is empty) |
| `PORT` | `8080` | HTTP port (any platform; Cloud Run injects `PORT`) |
| `WEB_DIR` | `web` | Static UI directory |
| `MOCK_EVENTS_DIR` | `mock/events` | Fixture JSONs |
| `*_API_KEY` | – | `OPENAI_/ANTHROPIC_/GOOGLE_API_KEY` per provider |
| `BEDROCK_MODEL_ID` | `us.amazon.nova-lite-v1:0` | Bedrock model |
| `OLLAMA_BASE_URL` | `localhost:11434` | Ollama server |
| `LLM_TIMEOUT_SECONDS` | `5` | Model call budget (→ Tier 1 only on timeout) |
| `RING_*` | – | Live Ring credentials (optional) |
| `RING_WEBHOOK_ENABLED` / `RING_WEBHOOK_SECRET` / `RING_SIGNATURE_HEADER` | false / – / `X-Signature` | Webhook HMAC verify (Partner API) |
| `RING_API_BASE_URL` | `https://api.amazonvision.com` | Ring Partner API base |
| `MCP_HTTP_TOKEN` | – | Bearer token for MCP HTTP (demo mode; replaced by OAuth when enabled) |
| `MCP_ORIGIN` | – | Optional allowed Origin(s) (host or full URL), comma-separated |
| `OAUTH_ISSUER` | – | OAuth 2.1 issuer (Cognito / Okta) — set → `/mcp` requires JWT; empty → falls back to `MCP_HTTP_TOKEN` |
| `OAUTH_JWKS_URL` / `OAUTH_AUDIENCE` / `MCP_RESOURCE` | – | JWKS discovery override, expected audience, RFC 8707 canonical URI |
| `OAUTH_REQUIRE_RESOURCE` | `false` | Strictly enforce `resource` claim on tokens |
| `CF_ACCESS_JWT_ENABLED` | `false` | Accept `Cf-Access-Jwt-Assertion` as user-tier token (Cloudflare Access) |
| `MCP_401_WWW_AUTHENTICATE` | `true` | `false` for Alexa+ (401 without `WWW-Authenticate`) |
| `CALENDAR_MCP_URL` / `CALENDAR_MCP_TOKEN` | – | Optional **Calendar MCP** join (J2): Tier 2 reads `list_events` and cites `calendar:` evidence; empty = standalone |
| `CONTEXT_BUDGET_MS` | `200` | Calendar-context budget; slower → `context_status=timeout`, fail-open |
| `ENRICH_BUDGET_MS` | `2000` | Documented Tier 2 enrichment budget (`LLM_TIMEOUT_SECONDS` bounds the model call) |
| `QUIET_HOURS_START` / `QUIET_HOURS_END` | – | Quiet-hours phrasing for night motion (UX only, never evidence) |
| `API_AUTH_DISABLED` / `API_TOKEN` | `true` / – | Gate `/api/*` on public deploys (Bearer, `?token=`, or cookie); UI bootstraps from `/?token=…` |
| `PURGE_INTERVAL_S` | `86400` | Scheduled retention purge cadence (startup purge always runs) |
| `DEMO_TOKEN` | – | Optional Bearer required by `/api/simulate` |
| `RATE_LIMIT_PER_MINUTE` | `30` | Per-IP webhook/simulate limiter |
| `DEBOUNCE_SECONDS` | `10` | Dedupe window (kind+device); also `meta.request_id` |
| `EVENT_TTL_DAYS` | `30` | Auto-purge events older than N days |

### LLM providers (LangChain abstraction)

All live providers go through one `ChatModel` interface + `with_structured_output(TriageResult)`,
so the LLM contract (§4.4) is enforced identically by every model. Switch providers with one env var:

| `LLM_PROVIDER` | Package | Default model overridden by `LLM_MODEL` |
|---|---|---|
| `stub` (offline) | none | deterministic fixtures |
| `bedrock` | `langchain-aws` | `us.amazon.nova-lite-v1:0` |
| `openai` | `langchain-openai` | `gpt-4o-mini` |
| `anthropic` | `langchain-anthropic` | `claude-3-5-haiku-latest` |
| `google` | `langchain-google-genai` | `gemini-2.0-flash` |
| `ollama` | `langchain-ollama` | `llama3.2` |

```bash
pip install -r requirements-llm.txt        # core stays langchain-free (stub works with only requirements.txt)
export LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=... LLM_MODEL=claude-3-5-sonnet-latest
python -m uvicorn backend.main:app --port 8080
```

### Tests

```bash
pip install -r requirements-dev.txt
pytest -q        # 268 tests: taxonomy, Ring Partner API v1.1 (HMAC, idempotency), grounding gate, door calendar, Calendar MCP, db (sqlite+postgres), MCP tools, API, consent-share, escalation, OAuth 2.1, captions/a11y, LLM factory
# Postgres path locally: TEST_POSTGRES_DSN=postgresql://user:pw@host/db pytest -q
# Container check:      scripts/smoke_docker.sh [image]
```

### MCP smoke test (no Alexa needed)

```bash
curl -s -X POST localhost:8080/mcp \
  -H 'Authorization: Bearer change-me' \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

curl -s -X POST localhost:8080/mcp \
  -H 'Authorization: Bearer change-me' \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_daily_summary","arguments":{}}}'
```

### Deploy & demo targets

**Local + simulation (recommended for the demo video)** — run all flows above, no cloud needed:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m uvicorn backend.main:app --port 8080        # MOCK_MODE + stub by default
# automated demo: .venv/bin/python scripts/demo_local.py
```

**Docker (same app, persistent volume):**

```bash
docker compose up --build            # open http://localhost:8080
# try a real LLM: LLM_PROVIDER=ollama docker compose up   (Ollama runs on the host)
```

**Fire TV on the LAN:** open `http://<lan-host>:8080` in the Silk browser on Fire TV
(or the Fire TV Simulator); the UI runs kiosk-style and SSE updates alerts live.

**GCP Cloud Run (public URL — convenient for testing MCP from a phone / sharing a link):**

```bash
gcloud auth login && gcloud config set project <project-id>
./scripts/deploy_cloudrun.sh <project-id> [region]   # builds from the Dockerfile, deploys, prints URL & token
```

Cloud Run caveat: SQLite is **ephemeral per instance** — fine for a demo, lost on restart. For
durability set `DB_URL=postgresql://user:pw@host:5432/db` (Cloud SQL / Neon / RDS all work) — the
repository already ships a Postgres dialect, no code changes. Bedrock/IAM still work from Cloud Run
because `LLM_PROVIDER=bedrock` only needs AWS credentials in the environment.

**Secrets per platform (env is fine for the demo):**

| Platform | How to inject |
|---|---|
| Local / Docker | `.env` (never committed) or `docker compose` env |
| GCP Cloud Run | Secret Manager + `--set-secrets KEY=secret:latest`; or `--set-env-vars` |
| AWS | SSM Parameter Store / Secrets Manager; Lambda env; ECS secrets |
| Cloudflare Workers/Containers | `wrangler secret put` |

Secrets to manage: `OPENAI_/ANTHROPIC_/GOOGLE_API_KEY`, `RING_WEBHOOK_SECRET`, `RING_ACCOUNT_TOKEN`,
`MCP_HTTP_TOKEN`, `OAUTH_*`, `DEMO_TOKEN`.

### Deploy anywhere, integrate Amazon hardware

**Thesis:** the *stack* is portable; the *integration surface* is Amazon. AccessBell is a software
layer — run it wherever you want, keep the Ring / Fire TV / Alexa+ experience.

| Layer | Portable? | Choices (wired in code, not aspirational) |
|---|---|---|
| Compute | ✅ anywhere | local `uvicorn` · Docker Compose · GCP Cloud Run (`scripts/deploy_cloudrun.sh`) · any VM/k8s |
| LLM | ✅ | `stub` · `ollama` · `openai` · `anthropic` · `google` · **`bedrock`** (AWS-native) |
| Identity (MCP OAuth 2.1) | ✅ | Okta · Auth0 · Keycloak · Cloudflare Access · **Cognito** (AWS-native) · local token |
| Data | ✅ | SQLite now; Postgres/Cloud SQL is a small repository swap, not a redesign |
| Device integration | ❌ deliberately Amazon | Ring webhook (HMAC) · Fire TV caption surface (SSE) · Alexa+ MCP tools (spec 2025-11-25) |

Defensible claim: **no infrastructure lock-in, native on the Amazon device ecosystem.** AWS-native
pieces (Bedrock, Cognito) are *options*, not requirements — the same image runs on GCP or a laptop
with `LLM_PROVIDER=stub`.

Precision when pitching:
- **Cloudflare:** the Python FastAPI app does **not** run on Workers (JS/TS runtime) as-is — use
  Cloudflare Containers, or keep Cloudflare for TLS/Zero Trust in front of the app. Access
  Managed OAuth / Access-as-OIDC remains a valid IdP choice.
- **Bedrock** needs AWS credentials regardless of where the app runs (Cloud Run included).

**One-liner:** *"Runs anywhere — laptop, Docker, Cloud Run, any VM. Speaks natively to the hardware
people already own: Ring, Fire TV, Alexa+."*

### Security model (implemented)

- Ring payloads: HMAC-SHA256 hex signature in `RING_SIGNATURE_HEADER` (default `X-Signature`,
  optional `sha256=` prefix), constant-time compare on **raw body**; retries deduped by
  `meta.request_id` via a hashed unique index (`event_hash`).
- `/api/*` is gated by `API_TOKEN` on public deploys (`API_AUTH_DISABLED=false`); all write endpoints
  are rate-limited per IP (`RATE_LIMIT_PER_MINUTE`).
- `/mcp` uses **OAuth 2.1 (JWKS-verified JWT, two-tier)** when `OAUTH_ISSUER` is set — service tokens
  cannot act for users; falls back to `MCP_HTTP_TOKEN` for offline demo. `MCP_ORIGIN` allowlist enforced.
- Events auto-purged after `EVENT_TTL_DAYS` (retention, no video archive).
- LLM output is **re-validated in code** (pydantic `TriageResult`): enum category, 0–1
  confidence, known evidence sources, non-empty captions, and a grounding rule — specific
  categories require `expected_context` / `calendar` / `user_label` / `snapshot` evidence or
  payload signal, else the result is demoted with `grounding=demoted_insufficient_evidence`.
- Escalation and share are the only outward actions: escalation (default OFF) is durable and
  at-most-once, share requires explicit consent; both are audited, and escalation audit rows cite
  the **`policy.yaml` version + SHA** (`GET /api/policy`).

### Latency SLO (p95) — budgets in code

| Path | Target | Hard rule |
|---|---|---|
| Webhook in → SSE `alert_raw` | **p95 < 200 ms** | rules + DB insert only; `tier1_ms` histogram |
| Context join (local) | p95 < 50 ms | indexed DB reads; `context_ms` |
| Calendar MCP (J2) | **≤ `CONTEXT_BUDGET_MS`** else skip | `httpx` timeout; fail-open `context_status=timeout` |
| Enrich → SSE `alert_enriched` | **p95 < 2 s** | `ENRICH_BUDGET_MS` hard `wait_for`; on fail keep Tier 1 (`enrichment_failed`) and **still arm escalation** |
| MCP tool (`/mcp` tools/call) | **p95 < 500 ms** | DB-only, no LLM inside a tool; `mcp_tool_ms` |
| Escalation fire | timeout ± 1 s after ingest | durable pending + at-most-once claim |

Measured per process in `/api/metrics` (`timers`: `tier1_ms`, `context_ms`, `enrich_ms`, `mcp_tool_ms`, `webhook_to_sse_ms`). Aggregates are in-memory and disposable; counters are fixture-derived until live data exists. Ring→cloud network delay cannot be guaranteed in-process — an optional poll backup (internal design) mitigates missed webhooks.

**Line:** *If we hear the door, you see it in under 200 ms; if the model or the calendar is slow, you still see the door.*

### How we know (fixture-derived, not production telemetry)

The grounding gate is measurable — same fixtures, three arms (`scripts/ablation_evidence.py`):

| Arm | Signal available | Category accuracy |
|---|---|---|
| `event_only` | event type only | 0.5 |
| `payload_hints` | demo label hints in the payload | 1.0 |
| `expected_window` | user-set expected window | 1.0 |

A specific claim (`MED_DELIVERY`, `PACKAGE_DELIVERY`, `FAMILY_VISITOR`) that lacks grounding is
**demoted in code** to `UNKNOWN_VISITOR` with status `demoted_insufficient_evidence`; the why-line
says so on screen. `GET /api/metrics` reports the same counters at runtime, clearly labelled as
fixture-derived.

---

## AWS services

| Service | Role |
|---|---|
| **Amazon Bedrock** | Triage + accessible phrasing (Converse API, structured JSON) |
| AWS Lambda *(optional)* | Host webhook / skill |
| IAM | `bedrock:InvokeModel` for runtime |

References:

- [Bedrock overview](https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html)  
- [Inference](https://docs.aws.amazon.com/bedrock/latest/userguide/inference.html)  
- [Structured output](https://docs.aws.amazon.com/bedrock/latest/userguide/structured-output.html)  

---

## Value to the Amazon ecosystem

AccessBell is designed as a **layer that makes existing Amazon products usable by more people** —
not a competing device or camera.

| Amazon product | What AccessBell adds | How it shows up |
|---|---|---|
| **Ring** | Door events become usable for deaf, blind and limited-mobility users, who today cannot act on a chime or a thumbnail | new audience for hardware + Protect, fewer "can't use it" returns |
| **Fire TV** | The largest screen in the home becomes an accessibility alert surface (large caption, urgency, bilingual) | daily habitual reason to keep the TV in the loop |
| **Alexa+** | A working MCP add-on: 11 tools covering alerts, context snapshot, daily brief, door calendar (add/list/clear expected context), replies, accessibility prefs and consent-based escalation | installs, voice sessions, tool calls |
| **Bedrock** | A repeatable, safe pattern: rules first, structured `TriageResult`, evidence + confidence, grounding that refuses to invent | steady, low-cost inference per household |
| **AWS (runtime)** | One container, Postgres-optional, deployable in a customer's own AWS account | Marketplace-style service delivery |

**Positioning:** we do not ask Amazon to build accessibility; we ship it on top of what they already
sell, and measure success in *their* metrics — attach, renewal, sessions, tool calls.

---

## Ring integration

| Capability | Use |
|---|---|
| Webhook events (`button_press`, `motion_detected`, …) | Primary trigger |
| HMAC-SHA256 (`X-Signature: sha256=<hex>`) | Verify payloads (raw body) |
| Device discovery | List doorbell / cameras (`api.amazonvision.com`) |
| Image snapshot *(optional)* | One-frame share / richer triage — no video archive |
| Sandbox / personal account | Test without production publish (no physical device required to develop) |

Docs:

- [Ring Getting Started](https://developer.amazon.com/docs/ring/get-started.html)  
- [Ring Partner API](https://developer.amazon.com/docs/ring/api-documentation.html)  
- [Developer portal](https://developer.amazon.com/ring/console)  

---

## Fire TV

Fire TV supports **web apps**, React Native, and Android on Fire OS / Vega OS.  
AccessBell ships a **kiosk web UI** + SSE. Try it on a **physical Fire TV** with the official
[Web App Tester](https://developer.amazon.com/docs/fire-tv/webapp-app-tester.html) loading a LAN
URL, or open the same UI in any browser for development.

---

## Alexa+ / MCP

AccessBell exposes a **self-hosted MCP server** at `POST /mcp` (JSON-RPC 2.0, **Streamable HTTP**,
spec **2025-11-25+**). It is designed to sit **beside** other MCP servers — e.g. a Calendar MCP —
with **Alexa+** as the orchestrator that calls the right tool for the job.

| Tool | Description |
|---|---|
| `get_door_alerts` | List alerts by time / urgency |
| `get_event_detail` | One event with evidence |
| `get_context_snapshot` | Transparency: local context inputs used (expected/labels/hints) |
| `get_daily_summary` | Accessible daily brief |
| `add_expected_context` | Door intent — *“expect pharmacy ~10am”* |
| `list_expected_context` | Read the door calendar (active + upcoming windows) |
| `clear_expected_context` | Revoke a door-intent window by id or label |
| `confirm_event` | User ground-truth label |
| `send_quick_reply` | Leave / coming / not now |
| `update_accessibility_prefs` | Caption vs voice profile |
| `set_escalation` | *“If nobody answers, tell Lan”* — consent safety net |

**Orchestration example (multi-MCP):**

```
User: "Alexa, I expect a pharmacy delivery around 10."
Alexa+ → Calendar MCP.create_event(...)          # if a calendar server is connected
Alexa+ → AccessBell.add_expected_context(...)    # door intent for triage evidence
... later ...
Ring webhook → AccessBell → grounded caption on Fire TV
```

Any MCP client can call the same server (`tools/list` / `tools/call`). For a production Alexa+
connection: HTTPS + OAuth 2.1/PKCE; set `MCP_401_WWW_AUTHENTICATE=false` (Alexa+ checklist: 401
without `WWW-Authenticate`). See
[MCP Toolkit](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-overview.html).

---

## Design principles

1. **Event-driven** — no 24/7 video upload.  
2. **Rules first, LLM second** — low latency, lower cost, fewer hallucinations.  
3. **Evidence over invention** — if confidence is low, say “Someone is at the door.”  
4. **User agency** — briefs are for the resident household; sharing is opt-in with audit trail.  
5. **No medical claims** — logistics + accessibility only; not EMS, not diagnosis.  
6. **Local-first demo** — you can run the full experience without flaky live APIs.  
7. **Same stack, many homes** — elder, child-at-home, multi-gen home share one event pipeline.

---

## Ethics & privacy

- Do **not** use AccessBell to covertly monitor household members.  
- Face recognition is **out of scope** on purpose.  
- Snapshot frames (if enabled) are single-event and **not** a video archive.  
- Share / escalation are logged; the resident can revoke.  
- Child-at-home uses the **same** consent gate — the child still sees the TV caption (not secret
  monitoring); the parent is notified only per policy.

---

## Product story (3 minutes — one door, three people)

1. **Frame:** Hoa in the kitchen, An (10) in the living room, a parent at work. Most door apps
   assume a phone chime is enough.  
2. **See:** ring → Fire TV full-screen caption in &lt;200 ms.  
3. **Understand:** enrichment → “Possible package delivery” + confidence + evidence.  
4. **Act:** An uses the **TV remote** → “Leave at door.”  
5. **Protect:** *“If nobody answers, tell Mom.”* High-urgency, no reply → parent
   notified; audit row; reply in time stops it; revoke → silence.  
6. **Equity:** Ring AI subscription features off → the experience still works.  
7. **Close:** *“Accessibility isn’t a skin on a door app — it’s the architecture.”*

Drive the whole thing with one command (beats, waits, and the measured proof for each step):

```bash
.venv/bin/python -m uvicorn backend.main:app --port 8080      # MOCK_MODE + stub
.venv/bin/python scripts/demo_story.py --pace 3               # add --calendar http://127.0.0.1:8085/mcp for the multi-MCP cut
```

---

## Who it is for

| | |
|---|---|
| **Residents** who want a door they can understand — hearing, vision, mobility, language, or age |
| **Families** who want a calm safety net, not always-on cameras |
| **Builders** extending Ring / Fire TV / Alexa+ with a privacy-first accessibility layer |

---

## Roadmap

### Shipped (MVP)

| | |
|---|---|
| Ring webhook ingest (HMAC, Partner API v1.1 shape) + mock fixtures | ✅ |
| Tier 1 fast captions + Tier 2 grounded triage (Bedrock / stub) | ✅ |
| Fire TV / PWA web UI (SSE, D-pad, EN/VI) | ✅ |
| AccessBell MCP (10 door tools, Streamable HTTP) | ✅ |
| Consent escalation, audit, quick replies, daily brief | ✅ |
| Evidence gate status + why-line; door calendar `list`/`clear` | ✅ |
| Calendar MCP join (J2, optional); local stub for demo | ✅ |
| Child-safe captions; share protocol (preview/apply/read-back/revoke) | ✅ |
| Ablation script, metrics endpoint, docs-consistency check | ✅ |

### Next (production path)

| Focus | Intent |
|---|---|
| **Live Ring sandbox** | Real webhook credentials + end-to-end device events |
| **Durable deploy** | HTTPS + Postgres; secrets via cloud secret stores |
| **Alexa+ connection** | OAuth 2.1 / PKCE + MCP mode tuned for Alexa+ clients |
| **One-frame share** | Optional snapshot in consented messages — never a video archive |

### Later (opt-in)

| Focus | Intent |
|---|---|
| **One-frame share** | Optional snapshot in consented messages — never a video archive |
| **Richer voice history** | Natural door Q&A with event citations |
| **Speak-at-door replies** | Where device APIs allow |
| **Store readiness** | Ring / Alexa+ listing assets, privacy policy, certification |

### Deliberately out of scope

Face recognition · location tracking of children · scraping private email/calendars · medical
monitoring or EMS · 24/7 video analytics.

---

## License

MIT — see [LICENSE](LICENSE).

---

## Links

| | |
|---|---|
| Architecture | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Deployment | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |
| MCP transport spec | https://modelcontextprotocol.io/specification/2025-11-25/basic/transports |
| Alexa+ MCP Toolkit | https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-overview.html |
| Ring Partner API | https://developer.amazon.com/docs/ring/api-documentation.html |
| Fire TV web apps | https://developer.amazon.com/docs/fire-tv/getting-started-with-web-apps.html |
| Fire TV Web App Tester | https://developer.amazon.com/docs/fire-tv/webapp-app-tester.html |
| Bedrock | https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html |
