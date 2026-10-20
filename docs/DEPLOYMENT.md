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
| **AWS (ECS Fargate + ALB)** | `scripts/deploy_aws.sh [region]` (CDK) | RDS Postgres | Turnkey Fargate, ALB (idle timeout 300s for SSE), Cognito OAuth 2.1, Bedrock IAM (`LLM_PROVIDER=bedrock`), EventBridge bus, Secrets Manager-generated API/MCP/webhook tokens. Set `CERTIFICATE_ARN` for HTTPS; Ring requires an HTTPS callback |
| **GCP Cloud Run** | `scripts/deploy_cloudrun.sh <project> [region]` | SQLite is ephemeral → use Postgres | scale-to-zero (`min-instances 0`) is safe; REST gated by `API_TOKEN` |
| **Cloudflare** | Containers (or TLS/Zero Trust in front) | external Postgres | Python does **not** run on Workers |
| **VM / k8s** | container + `DB_URL` | Postgres | `/health` healthcheck |

Required for MCP over the public internet: **HTTPS + OAuth 2.1**. During development, use
`cloudflared tunnel` to get a public URL.

### 3c. Live demo instance (this submission)

| | |
|---|---|
| URL | http://Access-Acces-v4CzPoNSYUTf-590730701.us-east-1.elb.amazonaws.com |
| Region / stack | `us-east-1` · `AccessBellStack` (CDK, `scripts/deploy_aws.sh us-east-1`) |
| What is real | ECS Fargate task (public subnet, ALB target group), RDS Postgres 16 (`db.t4g.micro`), Cognito user pool + OAuth 2.1 resource server, EventBridge bus, Secrets Manager tokens, CloudWatch logs, the signed Ring v1.1 simulator, the MCP server, and the Gatekeeper |
| Demo mode | `MOCK_MODE=true` so the in-app Ring simulator and the Alexa+ client panel are visible; `LLM_PROVIDER=stub` so triage is deterministic and free — **this account has no Amazon Bedrock model access** (`Access to Bedrock models is not allowed for this account`), so the live instance runs the stub provider. The CDK default is still `LLM_PROVIDER=bedrock`; a Bedrock-capable account gets grounded Bedrock captions with no code change |
| Access | the UI is public; `/api/*` needs the API token. Open `/?token=<API_TOKEN>` once and the browser keeps it in the `accessbell_token` cookie. The token lives in Secrets Manager (`ApiTokenSecretArn` output) and is **not** committed |
| HTTPS | disabled (no ACM certificate in this account). Ring requires an HTTPS callback, so a real Ring app needs `CERTIFICATE_ARN` |
| Teardown | `cdk destroy` in `infra/`, or `aws cloudformation delete-stack --stack-name AccessBellStack` (RDS and the secrets use `RemovalPolicy.DESTROY`) |

### 3b. Portability matrix

The *stack* is portable; the *integration surface* is Amazon. AWS-native pieces (Bedrock, Cognito)
are options, not requirements — the same image runs on GCP or a laptop with `LLM_PROVIDER=stub`.

| Layer | Portable? | Choices (wired in code, not aspirational) |
|---|---|---|
| Compute | yes | local `uvicorn` · Docker Compose · GCP Cloud Run · AWS ECS Fargate (CDK) · any VM/k8s |
| LLM | yes | `stub` · `ollama` · `openai` · `anthropic` · `google` · `bedrock` (AWS-native, default in CDK) |
| Identity (MCP OAuth 2.1) | yes | Okta · Auth0 · Keycloak · Cloudflare Access · Cognito (AWS-native) · local token |
| Data | yes | SQLite (default) · Postgres / Cloud SQL / RDS (same code, dialect swap) |
| Device integration | deliberately Amazon | Ring webhook (HMAC) · Fire TV caption surface (SSE) · Alexa+ MCP tools (spec 2025-11-25+) |

Cloudflare note: the Python FastAPI app does **not** run on Workers as-is; use Cloudflare Containers
or keep Cloudflare for TLS/Zero Trust in front of the app. Bedrock needs AWS credentials regardless
of where the app runs.

### 3a. Ring-compatible HTTPS and Alexa+ OAuth

The CDK stack exposes HTTP by default so it can be smoke-tested without a domain. Ring requires an
HTTPS callback, so for a real Ring app create an ACM certificate for your domain and deploy with:

```bash
export CERTIFICATE_ARN=arn:aws:acm:<region>:<account>:certificate/<id>
export ALEXA_CALLBACK_URLS=https://<your-alexa-callback>   # optional; enables auth-code + PKCE
./scripts/deploy_aws.sh <region>
```

With `CERTIFICATE_ARN` set, the stack adds an HTTPS listener, redirects HTTP to HTTPS, and prints
`ServiceUrl` / `RingWebhookUrl` using `https://`. Without it, those outputs are HTTP and are **not**
Ring-callback compatible.

The service client uses Cognito `client_credentials` for discovery/ping only (`mcp:service`). The
optional Alexa+ client uses authorization-code grant with `mcp:tools` / `mcp:resources`; set
`ALEXA_CALLBACK_URLS` to the callback registered with your Alexa+ MCP integration. Both client IDs
are passed to the app as `OAUTH_CLIENT_IDS`. Cognito does not allow `client_credentials` and
authorization-code grant on the same app client, which is why the stack creates two clients.

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
| Runtime | `APP_ENV`, `PORT`, `WEB_DIR`, `LOG_LEVEL`, `MOCK_MODE`, `FORWARDED_ALLOW_IPS` |
| Storage | `DB_URL` (or `DB_PATH`) |
| LLM / AWS | `LLM_PROVIDER`, `LLM_MODEL`, `*_API_KEY`, `AWS_REGION`, `LLM_TIMEOUT_SECONDS`, `EVENTBRIDGE_BUS_NAME` |
| API auth (REST/SSE) | `API_AUTH_DISABLED`, `API_TOKEN` |
| MCP / auth | `MCP_HTTP_TOKEN`, `MCP_ORIGIN`, `OAUTH_ISSUER`, `OAUTH_JWKS_URL`, `OAUTH_AUDIENCE`, `OAUTH_CLIENT_IDS`, `OAUTH_SCOPE_PREFIX`, `MCP_RESOURCE`, `OAUTH_REQUIRE_RESOURCE`, `CF_ACCESS_JWT_ENABLED`, `MCP_401_WWW_AUTHENTICATE` |
| Outbound notifications | `NOTIFIER_PROVIDER`, `SNS_TOPIC_ARN`, `SES_SENDER_EMAIL`, `ANNOUNCE_ENABLED` |
| Ring | `RING_WEBHOOK_ENABLED`, `RING_WEBHOOK_SECRET`, `RING_SIGNATURE_HEADER`, `RING_API_BASE_URL`, `RING_ACCOUNT_TOKEN` |
| Calendar MCP (J2, optional) | `CALENDAR_MCP_URL`, `CALENDAR_MCP_TOKEN` |
| Latency budgets | `CONTEXT_BUDGET_MS`, `ENRICH_BUDGET_MS`, `QUIET_HOURS_START`, `QUIET_HOURS_END` |
| Ops | `DEMO_TOKEN`, `RATE_LIMIT_PER_MINUTE`, `DEBOUNCE_SECONDS`, `EVENT_TTL_DAYS`, `PURGE_INTERVAL_S` |
| AWS deploy only (not read by the app) | `CERTIFICATE_ARN`, `ALEXA_CALLBACK_URLS` |

Secrets: **GCP Secret Manager** (`--set-secrets`), **AWS SSM/Secrets Manager**, **Cloudflare**
(`wrangler secret put`), or a local `.env` (never committed).

`FORWARDED_ALLOW_IPS` semantics: empty (default) ignores `X-Forwarded-For` entirely and rate-limits
by socket peer; a comma-separated list of exact IPs or CIDRs makes the app trust `X-Forwarded-For`
**only from those peers** (the CDK stack passes the VPC CIDR so ALB traffic resolves the real client
IP); `*` trusts any peer and should be used only behind a proxy you control.

The CDK stack generates `API_TOKEN`, `MCP_HTTP_TOKEN` and `RING_WEBHOOK_SECRET` in Secrets Manager
(no default secrets ship in code). Read them after deploy:

```bash
aws secretsmanager get-secret-value --secret-id <ApiTokenSecretArn output> --query SecretString --output text
```

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

`​.github/workflows/ci.yml` — four jobs: `test` (SQLite pytest + docs-consistency + ablation + labeled triage eval + latency
smoke) · `a11y` (pa11y WCAG2AA on `/` and `/?lang=vi` against a live app with a simulated alert) ·
`test-postgres` (same suite with `TEST_POSTGRES_DSN`) · `docker` (build + `scripts/smoke_docker.sh`:
health → simulate → MCP → discovery).

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