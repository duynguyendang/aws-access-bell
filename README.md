# AccessBell

> **Accessible door intelligence: the doorbell as text, on the screens a household already owns.**
> Ring · Fire TV · Alexa+ (MCP) · AWS Bedrock

[![ci](https://github.com/duynguyendang/aws-access-bell/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/duynguyendang/aws-access-bell/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

AccessBell is a companion layer on Ring for one resident at a time: a deaf or hard-of-hearing person
at home who needs to know **who is at the door and whether to trust it** — on the TV, in Alexa, on
the phone. Low-vision and limited-mobility residents use the same path (voice + remote); the first
user is specific. It is not a new camera and not a caregiver surveillance product: the person who
lives there stays in control.

**Meet Mai.** 72, lives alone, hard of hearing. The doorbell rings while she is cooking; the TV shows
*Someone is at the door* in seconds, names the pharmacy courier with its evidence a moment later,
and she answers from the remote. That single flow is the product. (Mai is a composite of the
residents this is built for — no real person's data.)

**The part we are proudest of — the Gatekeeper.** Anyone can say “I'm the police.” AccessBell never
verifies a visitor claim from the visitor's own words: a claim is checked against independent
evidence (an expected window the resident created, a user label, a calendar event, a snapshot) and
comes out `verified`, `unverified`, or `contradiction` — with a risk level and a challenge question.
Unverified high-stakes claims are never softened into a friendly caption. The gate exists because
the claim at the door is a measured attack surface, not a thought experiment: the FTC's Consumer
Sentinel Data Book 2024 counts 845,806 imposter-scam reports and $2.95B in reported losses, with
government-impersonation losses alone at $789M (up $171M year over year) — and adults 70+ report
the highest median losses of any age group
([FTC, 2024](https://www.ftc.gov/reports/consumer-sentinel-network-data-book-2024)).

## Try it

| | |
|---|---|
| **Live demo** | _published with the submission_ <!-- TODO(submission): add the demo URL --> |
| **3-minute video** | _published with the submission_ <!-- TODO(submission): add the video link --> |
| **Run on AWS** | `./scripts/deploy_aws.sh [region]` → ECS Fargate + RDS Postgres + Cognito + EventBridge; **Bedrock is the triage model in this path** |
| **Run locally** | `pip install -r requirements-dev.txt && python -m backend` → http://localhost:8080 (offline test mode: `MOCK_MODE` + `stub`) |

## Evaluate it in 3 minutes

```bash
pip install -r requirements-dev.txt
python -m pytest -q                        # **331 tests** (298 pass + 33 Postgres-skipped)
python scripts/eval_triage.py              # 42 labeled scenarios: category + Gatekeeper + memory
python scripts/ablation_evidence.py        # grounding gate ablation (3 arms)
python scripts/measure_latency.py          # local Tier-1 / enrichment latency (stub)
DB_URL=sqlite:///demo.db MOCK_MODE=true python -m backend &   # then:
curl -X POST "http://127.0.0.1:8080/api/simulate?fixture=doorbell_police_claim"
curl -X POST "http://127.0.0.1:8080/api/simulate?fixture=doorbell_med"
```

What to look at: the alert caption and its **Evidence / Why** line; the Gatekeeper challenge on the
police claim; the grounding badge (`grounded` / `generic` / `demoted_insufficient_evidence`); the
`/api/metrics` timers; and **Download door log** — a plain-text artifact of the day's events you can
keep. A recording plan lives in [docs/DEMO.md](docs/DEMO.md).

## How it works

```
Ring webhook (HMAC) ──► AccessBell ──► Fire TV / PWA   (Tier 1 caption, rules only)
        or /api/simulate    │
                            ├─► Tier 2: grounded triage (Bedrock / stub) + expected windows
                            ├─► Gatekeeper: claim verification (verified / unverified / contradiction)
                            ├─► EventBridge (optional, off by default)
                            ├─► MCP server ◄──► Alexa+ ◄──► Calendar MCP
                            └─► consent escalation / share (opt-in, audited)
```

1. **Tier 1 (rules)** — instant “Someone is at the door”; never blocked on a model.
2. **Tier 2 (LLM)** — EN/VI captions with confidence + evidence, validated by a pydantic contract;
   specific categories without grounding evidence are **demoted in code**. LLM output never reaches
   a user unvalidated.
3. **Gatekeeper** — visitor claims (police / utility / government / pharmacy / package / family) are
   verified only by independent signals; otherwise `unverified` + risk + challenge question.
4. **Memory** — “same as last time” reply suggestion when the last reply for that door had the same
   category (one tap to reuse; never automatic).
5. **Talk** — door turns stored per event; a fixed-prompt EN/VI phrasebook with browser TTS. Free
   text is honestly labeled “no fixed-prompt translation” — never a fake translation.
6. **Protect** — unanswered high-urgency events can escalate to a contact the resident chose:
   default OFF, durable across restarts, at-most-once, audited, revocable.

Surfaces: **Fire TV / PWA web UI** (SSE live captions, urgency as text + color, D-pad navigation,
EN/VI, child mode, 44 px targets) and **Alexa+ via MCP** (Streamable HTTP, JSON-RPC 2.0, spec
2025-11-25+) with **11 tools**:

| Tool | Purpose | | Tool | Purpose |
|---|---|---|---|---|
| `get_door_alerts` | Alerts by time / urgency | | `confirm_event` | User ground-truth label |
| `get_event_detail` | One event + evidence | | `send_quick_reply` | Leave / coming / not now |
| `get_context_snapshot` | Context inputs used | | `update_accessibility_prefs` | Caption vs voice profile |
| `get_daily_summary` | Accessible daily brief | | `set_escalation` | Consent safety net |
| `add_expected_context` | Door intent (“pharmacy ~10”) | | `list_expected_context` | Read the door calendar |
| `clear_expected_context` | Revoke a window by id / label | | | |

## AWS services

AccessBell runs on AWS by default: the CDK stack deploys it with **Bedrock as the triage model**,
the EventBridge bus, Cognito OAuth and generated Secrets Manager values. The `stub` provider is the
offline test mode (deterministic, no credentials), not the product path.

| Service | Role |
|---|---|
| **Amazon Bedrock** | Tier-2 triage through LangChain `ChatBedrockConverse` + structured `TriageResult` (Nova Lite by default). The AWS deployment runs `LLM_PROVIDER=bedrock`. |
| **Amazon EventBridge** | Optional outbound integration: every triaged event is published to a custom bus (`EVENTBRIDGE_BUS_NAME`; empty = off). CDK creates the bus + IAM. |
| **Amazon Cognito** | OAuth 2.1 resource server for `/mcp` (two-tier: service vs user tokens) in the CDK stack. |
| **Amazon SNS / SES** | Escalation and announce transport (`NOTIFIER_PROVIDER=sns|ses|demo`). |
| **AWS CDK (ECS Fargate + ALB + RDS Postgres)** | One-command deploy with generated Secrets Manager values for API/MCP/webhook tokens. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). |
| **AWS Lambda** *(optional)* | Host the Ring webhook if you prefer serverless ingest. |

Local development defaults to the deterministic `stub` provider so tests and demos never depend on
network or credentials; switch with `LLM_PROVIDER=bedrock` (see `.env.example`). Other providers
(OpenAI, Anthropic, Google, Ollama) go through the same LangChain interface — the contract is
identical for every model.

## Evidence and SLO (no fabricated numbers)

| Path | Target | Hard rule |
|---|---|---|
| Webhook in → SSE `alert_raw` | **p95 < 200 ms** | rules + DB insert only |
| Calendar MCP context join | **≤ `CONTEXT_BUDGET_MS`** else skip | fail open, `context_status=timeout` |
| Enrich → SSE `alert_enriched` | **p95 < 2 s** | `ENRICH_BUDGET_MS` hard timeout; on failure keep Tier 1 and still arm escalation |
| MCP `tools/call` | **p95 < 500 ms** | DB-only; no LLM inside a tool |
| Escalation fire | timeout ± 1 s | durable pending + at-most-once claim |

Measured locally with `scripts/measure_latency.py` (100 simulated events, stub LLM, this repo;
numbers vary by machine and are not production telemetry): `tier1_ms` p95 **6.5 ms**, `enrich_ms`
p95 **12.3 ms**, `webhook_to_sse_ms` p95 **6.6 ms**. Budgets and live histograms are in `/api/metrics`.

Grounding is measurable, not asserted — same fixtures, three arms
(`scripts/ablation_evidence.py`): `event_only` 0.5, `payload_hints` 1.0, `expected_window` 1.0
category accuracy; and `scripts/eval_triage.py` runs 42 labeled scenarios covering the 5 categories,
Gatekeeper outcomes and memory (all rows and the source label are printed by the script).

Accessibility is enforced, not claimed: **pa11y WCAG2AA** runs in CI on `/` and `/?lang=vi` with a
simulated alert (zero reported issues), captions are EN+VI and TTS-safe by test, and D-pad
navigation reaches every visible control. Statement and known gaps:
[docs/ACCESSIBILITY.md](docs/ACCESSIBILITY.md).

## Security model

- Ring payloads: HMAC-SHA256 over the raw body, constant-time compare; retries deduped by
  `meta.request_id` via hashed unique index.
- `/api/*` gated by `API_TOKEN` on public deploys; write endpoints rate-limited per IP.
- **Proxy headers are not trusted by default**: `FORWARDED_ALLOW_IPS` is empty → the client IP is
  the socket peer; when set, it accepts exact IPs or CIDRs (the CDK stack trusts its VPC CIDR for
  the ALB) and `*` is an explicit trust-all.
- `/mcp` uses OAuth 2.1 (JWKS-verified JWT, two tiers) when configured, else `MCP_HTTP_TOKEN`;
  `MCP_ORIGIN` allowlist enforced.
- Deploys do not ship default secrets: the CDK stack generates Secrets Manager values for the API
  token, MCP token and Ring webhook secret.
- LLM output is re-validated in code (pydantic `TriageResult` + grounding rule); escalation and
  share are the only outward actions, both opt-in, audited and citing the `policy.yaml` version+hash.

## Deploy

```bash
docker compose up --build                        # local container, http://localhost:8080
./scripts/deploy_aws.sh [region]                  # ECS Fargate + ALB + RDS + Cognito + EventBridge (CDK)
./scripts/deploy_cloudrun.sh <project> [region]   # GCP Cloud Run (portable bonus; SQLite is ephemeral)
```

Secrets, scaling, go-live checklist and the portability matrix (compute / LLM / identity / data)
live in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). Simulation levels (L0 local → L3 hardware) are in
[docs/SIMULATION.md](docs/SIMULATION.md).

## Repository layout

```
aws-access-bell/
├── backend/            # FastAPI app: webhook, triage, Gatekeeper, captions, MCP, escalation, brief
│   ├── main.py         # routes, SSE stream, /mcp endpoint, metrics
│   ├── aws_events.py   # EventBridge publisher (off by default, fail open)
│   ├── captions.py     # EN/VI strings — single source, TTS-safe
│   ├── triage.py       # Tier 1 rules + Tier 2 pipeline + grounding gate + verification
│   ├── schema.sqlite.sql / schema.postgres.sql
│   └── llm/            # stub + LangChain provider factory (Bedrock/OpenAI/Anthropic/Google/Ollama)
├── infra/              # AWS CDK: ECS Fargate, ALB, RDS, Cognito, EventBridge, Bedrock IAM
├── web/                # Fire TV / PWA UI (SSE, D-pad, EN/VI)
├── mock/events/        # 7 fixture stories (Ring Partner API v1.1 envelopes)
├── prompts/triage.txt  # LLM prompt: TriageResult contract + guardrails
├── scripts/            # demo_story.py, eval_triage.py, measure_latency.py, ablation_evidence.py, deploy_*
├── docs/               # ARCHITECTURE, DEPLOYMENT, SIMULATION, ACCESSIBILITY, DEMO
└── tests/              # pytest: sqlite + postgres, triage, captions/a11y, MCP, API, escalation, ...
```

## Environment

All variables are documented in `.env.example`; the full table with platform notes is in
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). The most used:

| Variable | Default | Purpose |
|---|---|---|
| `MOCK_MODE` | `true` | Fixtures instead of live Ring |
| `LLM_PROVIDER` / `LLM_MODEL` / `LLM_TIMEOUT_SECONDS` | `stub` / provider default / `5` | `stub` \| `bedrock` \| `openai` \| `anthropic` \| `google` \| `ollama`; AWS deploys use `bedrock` |
| `DB_URL` / `DB_PATH` | `sqlite:///accessbell.db` | SQLite or Postgres; `POSTGRES_HOST/PORT/USER/PASSWORD/DB` build the DSN |
| `PORT` / `WEB_DIR` / `MOCK_EVENTS_DIR` / `LOG_LEVEL` / `APP_ENV` | `8080` / `web` / `mock/events` / `INFO` / `development` | Runtime basics |
| `AWS_REGION` / `BEDROCK_MODEL_ID` | `us-east-1` / `us.amazon.nova-lite-v1:0` | Bedrock model and region |
| `EVENTBRIDGE_BUS_NAME` | – | Publish triaged events to EventBridge; empty = off |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` / `OLLAMA_BASE_URL` | – | Alternative LLM providers |
| `RING_WEBHOOK_ENABLED` / `RING_WEBHOOK_SECRET` / `RING_SIGNATURE_HEADER` | `false` / – / `X-Signature` | Webhook HMAC verification |
| `RING_CLIENT_ID` / `RING_CLIENT_SECRET` / `RING_ACCOUNT_TOKEN` / `RING_API_BASE_URL` | – / – / – / `https://api.amazonvision.com` | Ring Partner API client (optional) |
| `MCP_HTTP_TOKEN` / `MCP_ORIGIN` | – | MCP bearer token (demo) + allowed Origins |
| `OAUTH_ISSUER` / `OAUTH_JWKS_URL` / `OAUTH_AUDIENCE` / `MCP_RESOURCE` / `OAUTH_REQUIRE_RESOURCE` | – | OAuth 2.1 resource server (`/mcp`) |
| `OAUTH_SCOPE_PREFIX` / `OAUTH_CLIENT_IDS` / `CF_ACCESS_JWT_ENABLED` / `MCP_401_WWW_AUTHENTICATE` | – / – / `false` / `true` | Scope/client checks, Cloudflare Access tokens, Alexa+ 401 shape |
| `CALENDAR_MCP_URL` / `CALENDAR_MCP_TOKEN` | – | Optional Calendar MCP join (off by default) |
| `CONTEXT_BUDGET_MS` / `ENRICH_BUDGET_MS` | `200` / `2000` | Latency budgets (fail open) |
| `QUIET_HOURS_START` / `QUIET_HOURS_END` | – | Calmer night phrasing (UX only, never evidence) |
| `API_AUTH_DISABLED` / `API_TOKEN` / `DEMO_TOKEN` | `true` / – / – | Gate `/api/*` on public deploys; optional token for `/api/simulate` |
| `RATE_LIMIT_PER_MINUTE` / `DEBOUNCE_SECONDS` / `EVENT_TTL_DAYS` / `PURGE_INTERVAL_S` | `30` / `10` / `30` / `86400` | Limiter, dedupe, retention |
| `NOTIFIER_PROVIDER` / `SNS_TOPIC_ARN` / `SES_SENDER_EMAIL` / `ANNOUNCE_ENABLED` | `log` / – / – / `false` | Announce / escalation transport |
| `FORWARDED_ALLOW_IPS` | empty | Trusted proxy IPs/CIDRs for the real client IP; empty ignores `X-Forwarded-For`; `*` trusts any peer |

## Who it is for

| | |
|---|---|
| **Residents** | A door they can understand — hearing, vision, mobility, language or age |
| **Families** | A calm safety net instead of always-on cameras |
| **Builders** | A privacy-first accessibility layer on Ring / Fire TV / Alexa+ |

**Value to the Amazon ecosystem:** Ring events become usable for audiences that cannot act on a
chime or thumbnail; Fire TV becomes an accessibility alert surface; Alexa+ gets a working MCP add-on
(11 tools); Bedrock gets a low-cost, grounded inference pattern; all of it deploys inside a
customer's own AWS account. We measure success in attach, sessions and tool calls — mechanisms, not
invented numbers.

## Ethics & privacy

- No face recognition, no face embeddings; snapshot frames are single-event, never a video archive.
- Escalation and sharing are OFF by default, revocable, audited — and the resident is the user.
- Child mode is the same consent gate, not secret monitoring: the child sees the caption, a parent
  is contacted only when allowed and nobody answers.
- Not a medical or EMS product; logistics and accessibility only.

## Roadmap

| Shipped (MVP) | Next (production path) |
|---|---|
| Ring webhook (HMAC, Partner API v1.1) + fixtures; Tier 1 + grounded Tier 2 | Live Ring sandbox end-to-end |
| Gatekeeper verification; Memory; door-talk interpreter (fixed prompts, EN/VI) | Public HTTPS deploy + Postgres (CDK stack in `infra/`) |
| MCP server (11 tools); Calendar MCP join (optional); daily brief; share protocol | Alexa+ connection (OAuth 2.1 / PKCE, `MCP_401_WWW_AUTHENTICATE=false`) |
| Consent escalation (durable, at-most-once, audited); quiet hours; child captions | One-frame snapshot in consented share |
| Evidence tooling: eval (42 cases), ablation, latency, WCAG2AA CI, docs check | Richer voice history with event citations; speak-at-door replies where APIs allow |

**Out of scope on purpose:** face recognition · location tracking of children · scraping private
calendars/email · medical monitoring or EMS · 24/7 video analytics.

## License

MIT — see [LICENSE](LICENSE).

## Links

| | |
|---|---|
| Architecture | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Deployment & portability | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |
| Simulation guide (L0→L3) | [docs/SIMULATION.md](docs/SIMULATION.md) |
| Accessibility statement | [docs/ACCESSIBILITY.md](docs/ACCESSIBILITY.md) |
| Demo storyboard (3-min video) | [docs/DEMO.md](docs/DEMO.md) |
| MCP transport spec | https://modelcontextprotocol.io/specification/2025-11-25/basic/transports |
| Alexa+ MCP toolkit | https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-overview.html |
| Ring Partner API | https://developer.amazon.com/docs/ring/api-documentation.html |
| Bedrock | https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html |
