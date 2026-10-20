# Product feedback — every API, SDK, and tool used

Written for the Amazon App Dev 2026 submission. Each entry says what AccessBell used it for, what
worked, and the friction we actually hit. Where we did not have live access, we say so.

---

## Ring Partner API / Ring webhook v1.1

**Used for:** the runtime front door. `/webhooks/ring` parses the v1.1 envelope
(`meta.version/time/request_id/account_id`, `data.id/type/attributes.source/source_type/timestamp`),
verifies `X-Signature: sha256=<hmac-hex>` over the raw body, dedupes retries by `meta.request_id`,
and responds within Ring's 5-second delivery budget. The in-app simulator builds the same envelope,
signs it, verifies it, and routes it through the same handler.

**What worked well**

- The v1.1 envelope is compact and easy to reason about; `meta.request_id` is exactly the
  idempotency key a service needs.
- HMAC over the raw body is the right design for a webhook. Constant-time compare and a raw-body
  read before JSON parsing are straightforward in FastAPI.
- `data.attributes.source` / `source_type` give enough to separate a button press from motion
  without guessing from a label.

**Friction**

1. **No local Ring simulator or replay tool.** We could not exercise a Ring-shaped callback without
   a device/account, so we built `backend/ring_simulator.py` and a UI panel. Every team building a
   Ring integration will need the same thing.
2. **Signature header naming is ambiguous in examples.** We found references to both
   `X-Signature` and `X-Ring-Signature`; AccessBell accepts both, with `X-Signature` as the default.
   A single canonical example with exact bytes/canonicalization would remove a class of bugs.
3. **Payload examples disagree about extras.** Some samples showed `event_id`, `tags`, or
   `label_hint`; the documented v1.1 envelope does not. We removed those fields from the fixtures
   and made the simulator emit only the official envelope. A “strict payload” JSON schema next to
   the prose would help.
4. **No transcript field.** A door transcript would be the single most valuable input for
   accessibility, but it is not part of the webhook. We treat `visitor_statement` as an explicit
   AccessBell extension and say so in the README; it is not presented as a Ring field.
5. **Snapshots are out-of-band.** Fetching a snapshot is a separate API call, and it is tempting to
   treat it as identity evidence. We deliberately do not: no face recognition, no snapshot-based
   claim verification. If Ring adds a signed “person present” signal, document its trust boundary
   explicitly.

**Suggestions**

- Ship a public webhook sandbox that can emit a signed v1.1 event and replay a captured one.
- Publish a JSON Schema and a minimal/complete example for each event type.
- Document the exact signature header, encoding, and canonical body once, with a test vector.
- If a transcript is ever added, mark it as untrusted visitor input in the schema.

---

## Amazon Bedrock (via LangChain `ChatBedrockConverse`)

**Used for:** Tier-2 grounded triage. The CDK stack sets `LLM_PROVIDER=bedrock` and
`LLM_MODEL=us.amazon.nova-2-lite-v1:0`; the app uses `with_structured_output(TriageResult)` and
re-validates the result.

**What worked well**

- Structured output maps cleanly to a pydantic contract; the model does not get to hand us prose
  that bypasses validation.
- The Converse API is a good abstraction; the same code path works for other providers through
  LangChain.
- Nova Lite is fast and cheap enough for a door event; the latency budget is comfortable.

**Friction**

1. **Model access is account/region-specific.** A stack can synth successfully and still fail at
   runtime because the model or inference profile is not enabled. We document the model-access step,
   but the failure is easy to misread as an application bug.
2. **Model IDs and inference-profile IDs are different shapes** (`us.amazon.nova-2-lite-v1:0` vs a
   foundation-model ID). The error messages do not always distinguish “not enabled” from “wrong
   region” from “wrong ID”.
3. **No local Bedrock emulator.** The deterministic `stub` provider is essential for tests and
   recordings; we keep it as the default so CI never needs AWS credentials.
4. **Model access cannot be granted from the API in a restricted account.** During our live deploy
   `InvokeModel` returned `Error 002: Access to Bedrock models is not allowed for this account`, and
   `PutUseCaseForModelAccess` answered `Your account is not authorized to perform this action.
   Please create a support case`. With a correct region, model ID, and IAM policy, that reads like
   an application bug rather than an account-state problem.
5. **`GetFoundationModelAvailability` is the diagnostic that was missing.** It separates the four
   gates — EULA agreement, account entitlement, region availability, and authorization — and shows
   that in our account three are `AVAILABLE` while `authorizationStatus` is `NOT_AUTHORIZED` for
   every model we probed (95 text models in `us-east-1`, 17 regions). A one-line "is this account
   allowed to invoke this model" check would have saved the deploy debugging time.

**Suggestions**

- Surface a single “check model access” diagnostic in the Bedrock console for a given region/ID.
- Publish a scriptable way to check (and where possible request) foundation-model access, and say
  plainly when an account must open a support case instead.
- Include inference-profile examples next to foundation-model examples in the API docs.
- Publish a tiny structured-output example with the exact Converse parameters.

---

## AWS CDK (Python)

**Used for:** `infra/accessbell_stack.py` — VPC, RDS Postgres, ECS Fargate, ALB, Cognito, EventBridge,
Secrets Manager, CloudWatch Logs.

**What worked well**

- Typed constructs and `CfnOutput` make the stack reviewable; `cdk synth` caught real issues before
  deploy.
- `ecs.ContainerImage.from_asset` builds the same Dockerfile used locally.
- Secrets Manager generation avoids shipping default tokens.

**Friction**

1. **Cognito flow constraints are surprising.** `client_credentials` cannot be combined with
   authorization-code grant on the same app client. The first synth failed with
   `ClientCredentialsAuthFlowCannot`; we split the stack into a service client and an optional
   Alexa+ auth-code client.
2. **HTTPS is not turnkey.** An ALB needs an ACM certificate and a domain; Ring requires HTTPS. The
   stack now takes `CERTIFICATE_ARN` and adds an HTTPS listener + redirect, but a first-time builder
   may not realize the default HTTP listener is not Ring-compatible.
3. **`ListenerAction.redirect` API shape.** The Python signature uses `permanent=True`, not
   `status_code=...`; small, but the error is a raw `TypeError` during synth.
4. **Local `cdk synth` needs the JSII runtime and npm**, which is a heavier setup than a pure Python
   stack. It works, but it is a separate toolchain from the app's venv.

**Suggestions**

- A CDK example for “ALB + ACM + HTTPS redirect” with a placeholder certificate would save time.
- Make Cognito flow incompatibilities a synth-time error with a suggested split, not a runtime
  constraint discovered after writing the client.
- Document `ListenerAction.redirect(permanent=True)` in the Python reference examples.

---

## Amazon ECS Fargate + Application Load Balancer

**Used for:** the runtime container and public entry point; ALB idle timeout is 300 s so SSE
connections survive.

**What worked well**

- Fargate + a single task is a good fit for a small household service; no cluster management.
- The ALB health check on `/health` is simple and reliable.
- SSE works through the ALB with a longer idle timeout.

**Friction**

- **SSE is per-instance.** The broker is in process memory; with more than one task, a client only
  sees events from its own task. We document “pin one instance or add Postgres LISTEN/NOTIFY”; a
  managed fan-out would be nicer.
- **Public IP for outbound pulls.** The task is in a public subnet with a public IP so it can pull
  the image and call Bedrock without a NAT gateway. That is a cost trade-off and a security detail
  that deserves a first-class pattern.
- **No built-in scheduled task for retention.** The app purges on startup; a long-running service
  needs an EventBridge schedule or a sidecar for strict retention.

**Suggestions**

- Document the “public subnet + no NAT” pattern and its security caveats explicitly.
- Provide a reference for SSE behind an ALB (idle timeout, sticky sessions, fan-out).
- Make scheduled retention a small CDK pattern.

---

## Amazon RDS for PostgreSQL

**Used for:** durable events, expected windows, labels, door turns, escalation timers, audit logs.

**What worked well**

- The storage facade’s `?` → `%s` translation and `RETURNING id` support made SQLite/Postgres
  portability practical.
- RDS in private isolated subnets with a security-group rule is straightforward.
- The escalation claim is a single conditional `DELETE`, so multiple instances cannot double-send.

**Friction**

- **SQL dialect traps are real.** `SELECT DISTINCT … ORDER BY` a column not in the select list is
  invalid on Postgres; we fixed it by deduping in Python. SQLite accepts it, so a green local suite
  can hide a production failure.
- **Local Postgres testing is optional in CI.** The suite skips 37 variants without
  `TEST_POSTGRES_DSN`; we would prefer a containerized Postgres in CI to catch dialect drift.
- **RDS is the biggest fixed cost** for a household app; scale-to-zero is not available for RDS.

**Suggestions**

- A “portable SQL” lint rule or a dual-dialect test template would help.
- Document the exact `DISTINCT`/`ORDER BY` portability rule in the RDS or SQLAlchemy docs.
- Offer a low-cost Postgres option explicitly aimed at single-household apps.

---

## Amazon Cognito (OAuth 2.1 resource server)

**Used for:** `/mcp` JWT verification (JWKS, issuer, audience, scopes), service-to-service and
Alexa+ user flows.

**What worked well**

- Cognito’s JWKS endpoint and custom resource-server scopes map cleanly to the verifier.
- Two tiers (service vs user) are easy to express with scopes.
- The optional auth-code client lets Alexa+ act for a user without a custom IdP.

**Friction**

1. **One client cannot do both `client_credentials` and authorization-code grant.** We split into
   two clients and pass both IDs via `OAUTH_CLIENT_IDS`.
2. **Alexa+ callback registration is external.** The CDK stack needs the callback URL at deploy
   time; there is no one-click “connect Alexa+” flow. We made it optional via
   `ALEXA_CALLBACK_URLS`.
3. **No simple local token minting.** For offline tests we use a local token/JWKS fixture; Cognito
   itself is not available offline.

**Suggestions**

- Document the two-client pattern for machine + user flows in one user pool.
- Provide a local Cognito-compatible JWKS/token fixture for integration tests.
- Add a first-class “MCP OAuth client” template with the right scopes and callback settings.

---

## Amazon EventBridge

**Used for:** optional publication of every triaged event to a custom bus (`EVENTBRIDGE_BUS_NAME`;
empty = off).

**What worked well**

- A custom bus is a clean seam for automations (lights, caregiver notifications, analytics).
- The publisher fails open: a bus error never blocks the door alert.

**Friction**

- **Schema drift.** There is no shared schema between the app event and downstream consumers; we
  document the payload but do not publish a schema registry entry.
- **Local testing needs a mock.** We test the publisher adapter, not a live bus, to keep CI offline.

**Suggestions**

- Publish an EventBridge schema or a JSON Schema for common door-event payloads.
- Provide a local emulator or a documented “put-events to a log” test double.

---

## Amazon SNS and SES

**Used for:** optional escalation/announce transports (`NOTIFIER_PROVIDER=sns|ses`).

**What worked well**

- The notifier boundary is small and testable; demo mode logs instead of sending.
- SNS is a good fit for a caregiver SMS/email fan-out.

**Friction**

- **SES sandbox and verification** are easy to forget; a send can fail for reasons unrelated to the
  code.
- **No delivery receipt in the request path.** Escalation is at-most-once at the database level, but
  carrier/provider delivery is best-effort; we do not claim otherwise.

**Suggestions**

- A “sandbox checklist” in the SES docs for first send.
- Clear guidance on idempotency keys vs delivery guarantees for SNS/SES.

---

## MCP server / Alexa+ MCP toolkit

**Used for:** 11 tools over Streamable HTTP (JSON-RPC 2.0), spec 2025-11-25+, including
`get_door_alerts`, `get_event_detail`, `confirm_event`, `add_expected_context`, `get_daily_summary`,
and accessibility preferences.

**What worked well**

- The MCP tool model is a natural fit for a voice assistant: the door log becomes a set of
  read/confirm actions.
- Streamable HTTP is simple to run behind the existing FastAPI app.
- A single `/mcp` endpoint with OAuth scopes keeps the surface small.
- To demonstrate the surface without a device, the PWA has a mock-mode-only **Alexa+ MCP client
  (simulated)** panel. It runs `initialize`, `tools/list`, and `tools/call` on the same MCP server
  and tool set as Alexa+ (directly on `/mcp` locally, through the mock-mode bridge
  `/api/demo/mcp` on a deployed demo, because the browser never holds the MCP token). The panel is
  labeled as a simulator. It is a demo harness, not a claim of device testing.

**Friction**

1. **Alexa+ does not yet support `WWW-Authenticate` discovery.** We added
   `MCP_401_WWW_AUTHENTICATE` (default true, set false for Alexa+) so the 401 shape matches the
   client’s expectations. This is a compatibility switch every builder will need.
2. **No official local Alexa+ simulator.** `scripts/verify_mcp.py` boots the app and exercises
   `initialize`, `tools/list`, and `tools/call`; that is the closest we could get without a device.
3. **Spec versions move.** The 2025-11-25 revision is newer than many examples; pinning the
   Streamable HTTP behavior and testing `initialize` explicitly avoided surprises.
4. **OAuth + MCP is still fiddly.** Resource metadata, audience, and scopes have several knobs; a
   minimal reference server would help.

**Suggestions**

- Publish a “known Alexa+ 401 shape” note next to the MCP auth docs.
- Provide an official local mock Alexa+ client that speaks Streamable HTTP; our in-app panel is a
  minimal stand-in, not a substitute for the real client.
- Include a minimal OAuth 2.1 + MCP reference with service and user tiers.

---

## LangChain (supporting SDK)

**Used for:** provider-agnostic chat models and `with_structured_output`.

**What worked well**

- The same triage code runs on Bedrock, OpenAI, Anthropic, Google, Ollama, and the stub.
- Structured output + pydantic is a strong safety boundary.

**Friction**

- Provider-specific structured-output behavior varies; we re-validate everything and fall back to
  Tier 1.
- The stub provider is our own; keeping it in sync with the real contract is a maintenance cost.

---

## FastAPI / uvicorn / pydantic (supporting libraries)

**Used for:** HTTP API, SSE, request validation, settings.

**What worked well**

- Raw-body HMAC verification is straightforward with `await request.body()`.
- SSE via `StreamingResponse` works on every target we tested.
- Pydantic gives a clear contract for both API inputs and LLM output.

**Friction**

- SSE + multiple workers needs external fan-out; that is an architecture issue, not a FastAPI bug.
- TestClient’s background-task timing requires polling in a few tests; we made the helper explicit.

---

## Playwright / pa11y (verification tools)

**Used for:** screenshots, UI flow checks, and WCAG2AA smoke tests in CI.

**What worked well**

- Playwright can drive the Ring simulator panel and the D-pad-style controls deterministically.
- pa11y catches contrast/label regressions on both EN and VI pages.

**Friction**

- Headless Chromium’s cached browser version must match the Playwright package; we pinned an
  executable path in the local screenshot script.
- pa11y does not replace a human screen-reader audit; we state that limitation in
  `docs/ACCESSIBILITY.md`.

---

## Summary

The biggest API gap is not model quality or compute: it is **trusted context at the door**. Ring
gives us the event; Bedrock gives us language; neither tells us whether the stranger's claim is true.
AccessBell's Gatekeeper fills that gap with resident-created context. The product feedback above is
mostly about making that path easier to build, test, and verify without a physical device or a live
cloud account.
