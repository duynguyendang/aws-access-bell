# AccessBell — Technical Architecture & Deployment

See also: [ARCHITECTURE](ARCHITECTURE.md) (internal detail) · [README](../README.md)

---

## 1. System shape

A single Python process (FastAPI/uvicorn). Every outside dependency (LLM, IdP, database) is
**pluggable via config**, so the same image runs on many platforms.

```
Ring webhook · POST /api/simulate
        │  HMAC verify · rate limit · debounce
        ▼
┌───────────────────────────────────────────────────┐
│ CORE — one FastAPI process                        │
│   Tier 1 rules (<200 ms) → DB → SSE alert_raw     │
│   Tier 2 async LLM       → TriageResult → SSE     │
│   Escalation → escalation_pending → claim → notify│
└──────┬────────────────────┬──────────────────┬────┘
       ▼                    ▼                  ▼
   Storage              Surfaces           Outbound
   storage/sqlite.py    /   Fire TV + PWA  notifier: announce / SMS
   storage/postgres.py  /api/*   REST      ring_client (live mode)
   schema.{dialect}.sql /mcp   JSON-RPC    (all safe in mock)
                          ▲
                 OAuth 2.1 (JWKS) or MCP_HTTP_TOKEN
```

**Three main flows**

| Flow | Path |
|---|---|
| Alert | webhook/simulate → Tier 1 → DB + SSE `alert_raw` → (async) Tier 2 → DB + SSE `alert_enriched` |
| Escalation | enriched → write `escalation_pending(fire_at)` → on expiry: claim (DELETE) → notify + `escalation_log` |
| MCP | client → `/mcp` (verify JWT/JWKS + scope) → tool → DB → JSON-RPC response |

**Principles**

- **Rules first, LLM second:** Tier 1 performs no LLM I/O, so the alert never waits on a model.
- **Evidence-grounded:** LLM output is re-checked by pydantic plus a grounding rule; without
  evidence a specific claim is demoted to the generic caption (no invented identity).
- **Stateless outside the DB:** the process keeps no important state in memory (escalation lives in
  the database).
- **Provider-agnostic:** LLM (stub/ollama/openai/anthropic/google/bedrock), IdP (any JWKS issuer),
  DB (SQLite/Postgres) — switch via environment variables.

---

## 2. State and data

| State | Where | Notes |
|---|---|---|
| Events / triage / labels / expected context | DB | single source of truth |
| Pending escalations | `escalation_pending` (DB) | survives restarts; at-most-once claim |
| Audit (share, escalation) | `share_log`, `escalation_log` | append-only |
| SSE subscribers, asyncio timers | RAM | losing them on restart is **safe by design** (pending re-arms) |
| Secrets | env / platform secret store | tokens are never logged |

Retention: `EVENT_TTL_DAYS` (default 30) purged at startup; no video is stored.

---

## 3. Deployment targets

| Target | Command | Data | Notes |
|---|---|---|---|
| **Local (demo)** | `python -m backend` (honors `PORT`) | SQLite file | nothing else needed |
| **Docker** | `docker compose up --build` | `dbdata` volume | needs a Docker daemon |
| **GCP Cloud Run** | `scripts/deploy_cloudrun.sh <project> [region]` | SQLite is ephemeral → use Postgres | scale-to-zero (`min-instances 0`) is safe; REST gated by `API_TOKEN` |
| **AWS (ECS/EC2)** | same container | RDS Postgres | Bedrock needs IAM credentials |
| **Cloudflare** | Containers (or TLS/Zero Trust in front) | external Postgres | Python does **not** run on Workers |
| **VM / k8s** | container + `DB_URL` | Postgres | `/health` healthcheck |

Required for MCP over the public internet: **HTTPS + OAuth 2.1**. During development, use
`cloudflared tunnel` to get a public URL.

---

## 4. Scaling & reliability constraints

| Situation | Requirement |
|---|---|
| Single instance | SQLite is fine, or Postgres |
| Multiple instances / scale-to-zero | **Postgres required**; escalation still never double-sends thanks to the DELETE claim |
| SSE (Fire TV / PWA) | live connection; graceful shutdown closes subscribers with a sentinel. The broker is **per-instance** — with multiple instances a client only sees events ingested by its own instance (pin one instance, or add Postgres LISTEN/NOTIFY) |
| Slow or failing LLM | Tier 1 still shows; event marked `enrichment_failed` |
| Ring retry | dropped by `meta.request_id`; else debounce by `device_id + kind` within `DEBOUNCE_SECONDS` |
| One failing SQL statement | the facade rolls back, avoiding an "aborted transaction" (Postgres) |

---

## 5. Config & secrets

| Group | Variables |
|---|---|
| Runtime | `PORT`, `WEB_DIR`, `LOG_LEVEL`, `MOCK_MODE` |
| Storage | `DB_URL` (or `DB_PATH`) |
| LLM | `LLM_PROVIDER`, `LLM_MODEL`, `*_API_KEY`, `BEDROCK_MODEL_ID`, `AWS_REGION`, `LLM_TIMEOUT_SECONDS` |
| API auth (REST/SSE) | `API_AUTH_DISABLED`, `API_TOKEN` |
| MCP / auth | `MCP_HTTP_TOKEN`, `MCP_ORIGIN`, `OAUTH_ISSUER`, `OAUTH_JWKS_URL`, `OAUTH_AUDIENCE`, `MCP_RESOURCE`, `OAUTH_REQUIRE_RESOURCE`, `CF_ACCESS_JWT_ENABLED`, `MCP_401_WWW_AUTHENTICATE` |
| Ring | `RING_WEBHOOK_ENABLED`, `RING_WEBHOOK_SECRET`, `RING_SIGNATURE_HEADER`, `RING_API_BASE_URL`, `RING_ACCOUNT_TOKEN` |
| Calendar MCP (J2, optional) | `CALENDAR_MCP_URL`, `CALENDAR_MCP_TOKEN` |
| Latency budgets | `CONTEXT_BUDGET_MS`, `ENRICH_BUDGET_MS`, `QUIET_HOURS_START`, `QUIET_HOURS_END` |
| Ops | `DEMO_TOKEN`, `RATE_LIMIT_PER_MINUTE`, `DEBOUNCE_SECONDS`, `EVENT_TTL_DAYS`, `ANNOUNCE_ENABLED`, `PURGE_INTERVAL_S` |

Secrets: **GCP Secret Manager** (`--set-secrets`), **AWS SSM/Secrets Manager**, **Cloudflare**
(`wrangler secret put`), or a local `.env` (never committed).

---

## 5b. Who can call what

| Surface | Guard |
|---|---|
| `/webhooks/ring` | HMAC (`RING_WEBHOOK_SECRET`) + per-IP rate limit |
| `/api/*` | `API_TOKEN` when `API_AUTH_DISABLED=false` (Bearer header, `?token=`, or `accessbell_token` cookie) |
| `/mcp` | OAuth 2.1 JWT (two-tier) or `MCP_HTTP_TOKEN` in demo mode |
| `/`, `/assets`, `/health` | public; the UI bootstraps its cookie from `/?token=…` |

**A public deploy must set `API_AUTH_DISABLED=false` and a strong `API_TOKEN`** — otherwise door
history, escalation contacts and share actions are open to anyone who has the URL.

---

## 6. CI/CD

`​.github/workflows/ci.yml` — three jobs: `pytest` (SQLite) · `pytest` (Postgres service via
`TEST_POSTGRES_DSN`) · `docker build` + `scripts/smoke_docker.sh` (health → simulate → MCP →
discovery).

---

## 7. Go-live checklist (MCP for Alexa+)

1. Deploy behind **public HTTPS** (Cloud Run / VM + domain).
2. Enable **OAuth 2.1**: `OAUTH_ISSUER` + `OAUTH_AUDIENCE` + `MCP_RESOURCE`; pick an IdP
   (Okta / Keycloak / Cognito / …).
3. Set `DB_URL` to Postgres (durable + multi-instance).
4. `min-instances ≥ 1`; keep a healthcheck cycle.
5. Move secrets into a secret store — not into a committed env file.
6. `alexa-ai new mcp --mcp-server-url https://<host>/mcp` → deploy the add-on (once preview access
   is granted).
7. `curl -i /mcp` must return a **bare 401** for Alexa+ (`MCP_401_WWW_AUTHENTICATE=false`); for
   RFC 9728 clients keep the default `true` and assert `WWW-Authenticate` on the 401.
8. Set `API_AUTH_DISABLED=false` + `API_TOKEN`, open the UI via `/?token=…`, and confirm
   `curl /api/events` without a token returns **401**.
9. Smoke: `scripts/smoke_docker.sh` green; `pytest -q` green (including Postgres).