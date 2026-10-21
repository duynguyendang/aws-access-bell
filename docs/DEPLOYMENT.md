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

### 3c. Live demo instance (this submission)

| | |
|---|---|
| URL | http://Access-Acces-v4CzPoNSYUTf-590730701.us-east-1.elb.amazonaws.com |
| Region / stack | `us-east-1` · `AccessBellStack` (CDK, `scripts/deploy_aws.sh us-east-1`) |
| What is real | ECS Fargate task (public subnet, ALB target group), RDS Postgres 16 (`db.t4g.micro`), Cognito user pool + OAuth 2.1 resource server, EventBridge bus, Secrets Manager tokens, CloudWatch logs, the signed Ring v1.1 simulator, the MCP server, and the Gatekeeper |
| Demo mode | `MOCK_MODE=true` so the in-app Ring simulator and the Alexa+ client panel are visible. The task runs **`LLM_PROVIDER=bedrock`** (the real `ChatBedrockConverse` path), but **this account is not allowed to use foundation models**: every Converse call returns `Error 002: Access to Bedrock models is not allowed for this account`. The app fails open exactly as designed — Tier 1 + Gatekeeper captions, the challenge line, and the unverified/verified decision still work — and the UI says *"Tier 2 model unavailable — showing the tier 1 caption"* instead of pretending the model answered. A Bedrock-capable account needs no code change |
| Limits | `RATE_LIMIT_PER_MINUTE=50` (per client IP) on the write and demo endpoints; `API_AUTH_DISABLED=true` + `PUBLIC_DEMO_MODE=true` for open demo access |
| Bedrock preflight | `scripts/check_bedrock_access.py` probes `InvokeModel` for the account before a deploy. `scripts/deploy_aws.sh` runs it when `LLM_PROVIDER=bedrock` and stops with the account error instead of shipping a stack whose events all land in `enrichment_failed` (`ALLOW_BEDROCK_BLOCKED=1` overrides, which is how this demo instance was deployed) |
| Access | **open**: the instance runs `API_AUTH_DISABLED=true` + `PUBLIC_DEMO_MODE=true`, so the plain URL works for anyone (no token, no `?token=`). The Ring webhook (HMAC) and `/mcp` (Cognito OAuth / `MCP_HTTP_TOKEN`) stay protected. Writes are capped at 50 requests/minute per client IP |
| HTTPS | disabled (no ACM certificate in this account). Ring requires an HTTPS callback, so a real Ring app needs `CERTIFICATE_ARN` |
| Teardown | `cdk destroy` in `infra/`, or `aws cloudformation delete-stack --stack-name AccessBellStack` (RDS and the secrets use `RemovalPolicy.DESTROY`) |
| Keeping it up | The instance costs roughly **$50–55/month** (Fargate 0.25 vCPU, ALB, `db.t4g.micro`, no NAT). Keep it running through the judging window if the live URL matters to the submission; otherwise destroy it and let judges run `scripts/deploy_aws.sh` themselves. **The demo video does not print the ALB URL** — the opening card says "Run the whole stack yourself: `scripts/deploy_aws.sh`" — so a stopped instance can never leave a dead link on screen |

### 3d. Running the demo with a real LLM provider

The Bedrock path is the default, but a Bedrock-capable account is not always available (see
`scripts/check_bedrock_access.py`). The same triage code runs on any LangChain provider, so the
deployed demo can use a hosted model instead:

```bash
# 1. store the key in Secrets Manager (it never reaches the CloudFormation template)
aws secretsmanager create-secret --name AccessBellLlmApiKey --secret-string "$LLM_API_KEY"

# 2. deploy with that provider; the stack injects OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_API_KEY
LLM_PROVIDER=openai LLM_API_KEY_SECRET_NAME=AccessBellLlmApiKey scripts/deploy_aws.sh us-east-1
```

`LLM_PROVIDER=openai|anthropic|google|ollama` also rebuilds the image with the provider SDKs
(`INSTALL_LLM=true`). `LLM_API_KEY=<key>` alone is enough — the deploy script creates or updates the
secret first. The provider-specific model defaults are `gpt-4o-mini`, `claude-3-5-haiku-latest`, and
`gemini-2.0-flash`; override with `LLM_MODEL`.

### Deploying to another AWS account

`scripts/deploy_aws.sh` sources `aws.env` by default. To deploy with a different identity (an IAM
Identity Center login, a named profile, a personal account), skip that file and point the CLI and
CDK at the profile:

```bash
SKIP_AWS_ENV=1 AWS_PROFILE=my-profile LLM_PROVIDER=bedrock scripts/deploy_aws.sh us-east-1
```

The Bedrock preflight then probes **that** account, so the deploy only proceeds with a real model
behind it. The stack name is the same, but each account gets its own stack and its own ALB URL.

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
| API auth (REST/SSE) | `API_AUTH_DISABLED`, `API_TOKEN`, `PUBLIC_DEMO_MODE` |
| MCP / auth | `MCP_HTTP_TOKEN`, `MCP_ORIGIN`, `OAUTH_ISSUER`, `OAUTH_JWKS_URL`, `OAUTH_AUDIENCE`, `OAUTH_CLIENT_IDS`, `OAUTH_SCOPE_PREFIX`, `MCP_RESOURCE`, `OAUTH_REQUIRE_RESOURCE`, `CF_ACCESS_JWT_ENABLED`, `MCP_401_WWW_AUTHENTICATE` |
| Outbound notifications | `NOTIFIER_PROVIDER`, `SNS_TOPIC_ARN`, `SES_SENDER_EMAIL`, `ANNOUNCE_ENABLED` |
| Ring | `RING_WEBHOOK_ENABLED`, `RING_WEBHOOK_SECRET`, `RING_SIGNATURE_HEADER`, `RING_API_BASE_URL`, `RING_ACCOUNT_TOKEN` |
| Calendar MCP (J2, optional) | `CALENDAR_MCP_URL`, `CALENDAR_MCP_TOKEN` |
| Latency budgets | `CONTEXT_BUDGET_MS`, `ENRICH_BUDGET_MS`, `QUIET_HOURS_START`, `QUIET_HOURS_END` |
| Ops | `DEMO_TOKEN`, `RATE_LIMIT_PER_MINUTE`, `DEBOUNCE_SECONDS`, `EVENT_TTL_DAYS`, `PURGE_INTERVAL_S` |
| AWS deploy only (not read by the app) | `CERTIFICATE_ARN`, `ALEXA_CALLBACK_URLS`, `LLM_API_KEY`, `LLM_API_KEY_SECRET_NAME` |

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

A **public demo instance** (the hackathon live instance) is the deliberate exception: it runs
`API_AUTH_DISABLED=true` together with `PUBLIC_DEMO_MODE=true`, which is the only way the app may
start with an open API in `APP_ENV=production`. What stays protected even then:

| Surface | Guard in public-demo mode |
|---|---|
| `/webhooks/ring` | HMAC `RING_WEBHOOK_SECRET` — unchanged |
| `/mcp` | OAuth 2.1 (Cognito) or `MCP_HTTP_TOKEN` — unchanged |
| `/api/simulate`, `/api/simulate/ring`, `/api/demo/mcp`, `/webhooks/ring` | per-IP limiter, `RATE_LIMIT_PER_MINUTE=50` |
| read-only routes (`/api/events`, `/api/metrics`, `/api/brief`, …) | open, synthetic demo data only |

So the trade-off is explicit: anyone can fire demo Ring events and add door-calendar windows on that
one instance (which is what a judge needs to try the flow), while the webhook and the MCP tools stay
token-protected. The instance is disposable — `cdk destroy` removes it.

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