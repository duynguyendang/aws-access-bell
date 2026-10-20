# Friction log — Amazon App Dev 2026

A running log of the friction we actually hit while building AccessBell. Times are estimates, not
invoices. Each entry links to the code or doc that carries the workaround. This is also the honest
record of what we could **not** verify without a physical device or a paid cloud account.

Severity: **S1** blocks the demo, **S2** costs hours / changes architecture, **S3** paper cut.

---

## 1. Ring v1.1 examples did not match the fixtures we started with

- **When:** submission week (Oct 2026)
- **Area:** Ring Partner API / webhook
- **Severity:** S1
- **Symptom:** our first fixtures used a flat `event_id` plus `tags` / `label_hint`. The documented
  v1.1 envelope is `meta` + `data.attributes`, and real payloads do not carry those hint fields.
  The UI and tests were passing against a payload shape Ring would never send.
- **Impact:** ~3 hours rewriting fixtures, parser tests, and the E2E client; the Gatekeeper demo
  would have been built on a fake field.
- **Workaround:** replaced all fixtures with official v1.1 envelopes; removed `tags` / `label_hint`
  from the real path; kept them only as explicit demo inputs with an honesty note.
- **Evidence:** `mock/events/*.json`, `tests/simulators/ring_simulator.py`,
  `backend/webhook.py`, `docs/SIMULATION.md`.
- **What would help:** one canonical JSON Schema and a complete example per event type, plus a
  “strict payload” validator in the Ring docs.

## 2. Signature header naming is ambiguous

- **When:** submission week
- **Area:** Ring webhook security
- **Severity:** S2
- **Symptom:** examples and community notes mention both `X-Signature` and `X-Ring-Signature`.
  Guessing wrong means every live event is a 401.
- **Impact:** ~1 hour implementing and testing both, with `X-Signature` as the default.
- **Workaround:** `RING_SIGNATURE_HEADER` (default `X-Signature`) and a legacy alias; the simulator
  emits the official header and verifies it before handing the event to the handler.
- **Evidence:** `backend/webhook.py`, `backend/ring_simulator.py`, `.env.example`.
- **What would help:** one canonical header, encoding, and test vector in the Ring docs.

## 3. No Ring sandbox or replay tool

- **When:** submission week
- **Area:** Ring developer tooling
- **Severity:** S1
- **Symptom:** without a Ring device/account we could not produce a Ring-shaped callback, so we
  could not prove the runtime path end to end. A static fixture does not exercise signing,
  verification, debounce, SSE, or the simulator UI.
- **Impact:** ~4 hours building `backend/ring_simulator.py` and the in-app panel.
- **Workaround:** the simulator builds a real v1.1 envelope, signs it with HMAC-SHA256, verifies
  `X-Signature`, and calls the same `RingWebhookHandler` as `/webhooks/ring`. The UI shows
  `signature_valid: true` and the resulting event.
- **Evidence:** `backend/ring_simulator.py`, `POST /api/simulate/ring`, `docs/DEMO.md`.
- **What would help:** a public webhook sandbox that can emit and replay signed events.

## 4. The Gatekeeper was verifying claims from the wrong evidence

- **When:** submission week
- **Area:** product logic / evaluation
- **Severity:** S1
- **Symptom:** the first version could mark “police” as verified from a user label, a payload hint,
  or a snapshot. That is exactly the failure the product exists to prevent: the visitor's own
  words or a stale label become proof.
- **Impact:** ~5 hours rewriting `verify_claim`, the prompt, the eval labels, and the tests.
- **Workaround:** verification now uses **only** resident-created expected windows or calendar
  events. A snapshot, a prior label, and a visitor statement never verify a claim. The 46-case eval
  includes police/utility/government claims with and without a window, plus contradiction cases.
- **Evidence:** `backend/triage.py`, `tests/test_gatekeeper.py`, `scripts/eval_triage.py`,
  `docs/ARCHITECTURE.md` §3.6.
- **What would help:** a shared “trusted context” vocabulary for door products; today every team
  invents its own.

## 5. Snapshots are tempting identity evidence

- **When:** submission week
- **Area:** privacy / product scope
- **Severity:** S2
- **Symptom:** a snapshot is available out-of-band and looks like evidence. Using it for identity
  would require face analysis, which we refuse to do.
- **Impact:** ~1 hour removing snapshot from the evidence vocabulary and docs.
- **Workaround:** snapshots are not an evidence source; the product never claims visual identity.
  A single-frame snapshot is only a future consented-share feature, not a Gatekeeper input.
- **Evidence:** `backend/triage.py` (`KNOWN_EVIDENCE_SOURCES`), `prompts/triage.txt`,
  `docs/ARCHITECTURE.md`.
- **What would help:** explicit trust labels on any future person/identity signal.

## 6. v1.1 events have no top-level `event_id`, so SSE and UI actions diverged

- **When:** submission week
- **Area:** API / UI integration
- **Severity:** S2
- **Symptom:** the old simulator returned a string `evt_sim_...` that matched the SSE `event_id`.
  The v1.1 envelope has `data.id`, while the database has an internal numeric id. Door-talk and
  reply actions looked up the wrong identifier.
- **Impact:** ~1.5 hours debugging UI actions and E2E assertions.
- **Workaround:** SSE emits the internal numeric event id; `_find_event` accepts the internal id,
  the Ring `data.id`, or a legacy top-level `event_id`. The simulator returns both `event_id` and
  `ring_event_id`.
- **Evidence:** `backend/main.py` (`_find_event`, `_announce`), `tests/test_api.py`.
- **What would help:** a documented identity model for “provider event id vs service event id”.

## 7. E2E test compared int and str after the id change

- **When:** submission week
- **Area:** tests
- **Severity:** S3
- **Symptom:** `test_debounce` found zero enriched alerts because the SSE client stored `"1"` while
  the simulator returned `1`.
- **Impact:** ~30 minutes.
- **Workaround:** normalize both sides to strings in the E2E assertion.
- **Evidence:** `tests/e2e/test_full_flow.py`.

## 8. Cognito does not allow `client_credentials` and authorization-code grant on one client

- **When:** submission week
- **Area:** AWS CDK / Cognito
- **Severity:** S2
- **Symptom:** `cdk synth` failed with `ClientCredentialsAuthFlowCannot` when the stack tried to
  give one Alexa+ client both flows.
- **Impact:** ~1 hour restructuring the stack.
- **Workaround:** two clients: `accessbell-service` for `client_credentials`, and an optional
  `alexa-plus-mcp` client for authorization-code grant when `ALEXA_CALLBACK_URLS` is set. Both ids
  go into `OAUTH_CLIENT_IDS`.
- **Evidence:** `infra/accessbell_stack.py`, `docs/DEPLOYMENT.md` §3a.
- **What would help:** a CDK/Cognito example of the machine + user two-client pattern.

## 9. ALB is HTTP-only by default, but Ring requires HTTPS

- **When:** submission week
- **Area:** AWS deployment
- **Severity:** S1 for a real Ring callback, S2 for the demo
- **Symptom:** the first CDK stack exposed port 80 only. That is fine for a local smoke test and
  useless for Ring, which requires an HTTPS callback.
- **Impact:** ~1 hour adding an optional ACM certificate, HTTPS listener, and HTTP→HTTPS redirect.
- **Workaround:** set `CERTIFICATE_ARN`; the stack prints `RingWebhookUrl` with `https://`. Without
  a certificate the output is explicitly HTTP and documented as not Ring-compatible.
- **Evidence:** `infra/accessbell_stack.py`, `scripts/deploy_aws.sh`, `docs/AWS.md`.
- **What would help:** a one-command “ALB + ACM + HTTPS” CDK pattern.

## 10. `ListenerAction.redirect` Python signature differs from the console docs

- **When:** submission week
- **Area:** AWS CDK
- **Severity:** S3
- **Symptom:** `status_code="HTTP_301"` raised `TypeError`; the Python API uses `permanent=True`.
- **Impact:** ~20 minutes.
- **Workaround:** `permanent=True`.
- **Evidence:** `infra/accessbell_stack.py`.

## 11. Alexa+ does not support `WWW-Authenticate` discovery yet

- **When:** submission week
- **Area:** MCP / Alexa+
- **Severity:** S2
- **Symptom:** a standards-shaped 401 with `WWW-Authenticate` is not what the Alexa+ MCP client
  expects; the same server needs a different 401 shape for RFC 9728 demos.
- **Impact:** ~2 hours adding and testing `MCP_401_WWW_AUTHENTICATE`.
- **Workaround:** default true for standards demos; set false for Alexa+. `scripts/verify_mcp.py`
  exercises `initialize`, `tools/list`, and `tools/call` locally.
- **Evidence:** `backend/main.py`, `.env.example`, `docs/ARCHITECTURE.md` §12.
- **What would help:** a documented Alexa+ 401/auth checklist and a local mock client.

## 12. No physical Fire TV or Ring device; accessibility claims must stay narrow

- **When:** submission week
- **Area:** accessibility / demo
- **Severity:** S2
- **Symptom:** the UI is TV-first and D-pad navigable, but we could not run it on a Fire TV or a
  live Ring doorbell. It is also not a packaged Fire TV app.
- **Impact:** ~1 hour writing the honesty boundary into the docs and choosing the Ring track rather
  than the Fire TV track.
- **Workaround:** submit to the Ring track; describe Fire TV as a surface, not a packaged app. The
  accessibility statement lists what is automated (pa11y, contrast, labels) and what is not
  (human screen-reader audit, physical device).
- **Evidence:** `docs/ACCESSIBILITY.md`, `docs/SUBMISSION.md`, `docs/DEMO.md`.
- **What would help:** a hosted Fire TV/Vega simulator and a Ring device loaner program.

## 13. Playwright browser cache mismatch

- **When:** submission week
- **Area:** screenshot/demo tooling
- **Severity:** S3
- **Symptom:** the installed Playwright package expected a newer Chromium than the cached one;
  `browserType.launch` failed before any screenshot.
- **Impact:** ~20 minutes.
- **Workaround:** launch with the cached `chromium-1234` executable path in the local screenshot
  script. CI installs the matching browser.
- **Evidence:** screenshot workflow in `docs/DEMO.md`; no runtime dependency.
- **What would help:** clearer version pinning in Playwright’s launch error (it does name the
  expected path, which is how we fixed it).

## 14. Submission research: Devpost pages block automated fetch

- **When:** submission week
- **Area:** submission tooling (not product)
- **Severity:** S3
- **Symptom:** direct fetches of the Devpost rules returned 403; we used search results and the
  public pages for the deadline, tracks, and judging criteria.
- **Impact:** ~30 minutes.
- **Workaround:** verify the deadline and criteria from multiple public pages; keep the submission
  checklist in `docs/SUBMISSION.md`.
- **What would help:** a machine-readable rules/JSON endpoint or an official API for hackathon
  submissions.

## 15. Bedrock model access cannot be granted from the API in a restricted account

- **When:** submission week, during the live deploy
- **Area:** Amazon Bedrock
- **Severity:** S1 for the deployed demo, S3 for the code
- **Symptom:** the task called `us.amazon.nova-lite-v1:0` and got
  `Error 002: Access to Bedrock models is not allowed for this account`. `PutUseCaseForModelAccess`
  answered `Your account is not authorized to perform this action. Please create a support case`.
  The CDK stack, IAM role, and region were all correct, so the failure looked like an application
  bug for a while.
- **Impact:** ~1 hour of triage. It also changed what the live instance could honestly claim.
- **Workaround:** the deployed demo runs `LLM_PROVIDER=stub` (deterministic triage) while the CDK
  default stays `LLM_PROVIDER=bedrock`; the app fails open to Tier 1 + Gatekeeper captions if
  Bedrock ever errors. `scripts/check_bedrock_access.py` now probes the account before a deploy
  (the deploy script runs it and stops with this exact error), and the tier-2 failure is logged
  with its cause instead of only marking the event `enrichment_failed`.
- **Evidence:** `docs/DEPLOYMENT.md` §3c, `backend/llm.py`.
- **What would help:** a documented, scriptable way to check and request foundation-model access,
  and a clearer runtime error that says "this account has no model access" instead of an opaque
  `Error 002`.

## 16. A rolling ECS deploy deadlocked the new task on Postgres DDL locks

- **When:** submission week, during the live deploy
- **Area:** AWS deployment / Postgres
- **Severity:** S1
- **Symptom:** the new Fargate task never became healthy: the app printed `Waiting for application
  startup` forever. The schema script dropped and re-added the event foreign keys on every start;
  `ALTER TABLE` takes an `ACCESS EXCLUSIVE` lock, and the running task's connection was idle in a
  transaction, so the new task waited on the lock. The container health check failed, ECS restarted
  the container, and the deployment stalled until the old task was stopped.
- **Impact:** ~40 minutes, one failed deployment, and a brief 502 from the load balancer.
- **Workaround:** the foreign keys are now repaired by the Postgres dialect only when they are
  missing or lack `ON DELETE CASCADE`; DDL runs with `lock_timeout`, and `init_schema` retries
  instead of hanging. The next rolling deploy started in one second.
- **Evidence:** `backend/storage/postgres.py`, `backend/schema.postgres.sql`, `backend/db.py`,
  `docs/ARCHITECTURE.md` §4.3.
- **What would help:** an ECS deployment circuit breaker that fails fast (or a task-startup probe
  that reports the blocked statement), so a lock wait is visible in the deploy log.

---

## What this log changed in the product

1. The Ring path is now an **official v1.1 envelope + HMAC** path, not a fixture-shaped shortcut.
2. The Gatekeeper verifies **only resident-created context**; the eval and tests encode that rule.
3. The simulator is a first-class UI surface, so the demo exercises the same runtime code as a live
   Ring callback.
4. The AWS stack has an **optional HTTPS listener** and a **two-client Cognito** design.
5. The docs state the physical-device, live-AWS, and transcript-extension limits plainly.
6. A **live demo instance** is deployed from the same CDK stack (ECS Fargate + ALB + RDS Postgres +
   Cognito + EventBridge) and documented in `docs/DEPLOYMENT.md` §3c, including the Bedrock
   model-access limit of this account.
7. Postgres startup no longer takes a table lock, so a rolling deploy cannot deadlock the new task
   (see entry 16).

## Open friction (not resolved before submission)

- No live Ring device or Ring sandbox account: the v1.1 path is simulator-verified, not
  device-verified.
- The live AWS instance is a **demo deployment**, not a production service: HTTP only (no ACM
  certificate), one Fargate task, and the deterministic `stub` triage provider because this account
  has no Bedrock model access. See [DEPLOYMENT.md](DEPLOYMENT.md) §3c.
- No human screen-reader audit on a physical TV: automated accessibility checks pass, but that is
  not the same thing, and we do not claim it is.
- Alexa+ was exercised through the MCP protocol against the live MCP endpoint and an in-app client
  simulator, not through a physical Echo device.
