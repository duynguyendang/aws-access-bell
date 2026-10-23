# AccessBell — Amazon App Dev 2026 submission notes

**Project:** AccessBell — accessible door intelligence for the person who lives there
**Repository:** https://github.com/duynguyendang/aws-access-bell
**License:** MIT
**Tracks:** Ring track · AWS Builder mini challenge
**Supporting surface:** Alexa+ via MCP (not submitted as a separate track)
**Submission window:** 2026-08-31 → 2026-10-23; first commit **2026-09-22**

## Short description

AccessBell turns a Ring door event into accessible text on the screens a household already owns:
a TV-first PWA, Alexa+ tools over MCP, and a phone browser. It answers two questions in order:
*who is at the door* and *should I trust what they say*. The second question is the product.

A visitor's claim — "I'm the police", "I'm from the utility", "I have your prescription" — is never
verified by the visitor's own words, a previous user label, or an unanalysed snapshot. It is
verified only by a window or calendar event the resident created. Otherwise the headline says
*Visitor claims to be police. Not verified.*, with a risk label and a claim-specific challenge
question. This matters for deaf and hard-of-hearing residents, who cannot use tone of voice or a
quick glance through the peephole to judge a stranger.

## Why this is a Ring project

The runtime path is Ring Partner API **webhook v1.1**:

- `POST /webhooks/ring` accepts the official envelope (`meta.version/time/request_id/account_id`,
  `data.id/type/attributes.source/source_type/timestamp`).
- `X-Signature: sha256=<hmac-hex>` is verified over the raw body with a constant-time compare.
- Retries are deduped by `meta.request_id`.
- The in-app **Ring simulator** builds the same v1.1 envelope, signs it, verifies the signature, and
  passes it to the same `RingWebhookHandler`. The UI shows `signature_valid: true` and the resulting
  event, so the demo visibly exercises Ring technology rather than describing it.
- Snapshots are fetched out-of-band by the Ring API and are never treated as analysed identity
  evidence. There is no face recognition and no face embedding.

**Honest limitation:** the simulator's `data.attributes.visitor_statement` is an AccessBell
transcript extension, not a standard Ring field. Real Ring v1.1 webhooks do not include tags, label
hints, or a transcript. We say this explicitly in the README and demo.

## Why this empowers Alexa+ (Self-hosted MCP Server)

AccessBell directly embodies how brands in Preview are building and shipping experiences on Alexa+ that customers love:

- **Self-Hosted MCP Server**: Built on the open standard that powers Alexa+ integrations — Streamable HTTP transport, JSON-RPC 2.0, adhering to MCP spec **2025-11-25 or later** (`POST /mcp`).
- **11 Purpose-Built Tools**: Full suite of door intelligence tools (`get_door_alerts`, `get_event_detail`, `get_context_snapshot`, `confirm_event`, `send_quick_reply`, `add_expected_context`, `list_expected_context`, `clear_expected_context`, `update_accessibility_prefs`, `set_escalation`, `get_daily_summary`).
- **Two-Tier OAuth 2.1 Authentication**: Amazon Cognito resource-server verification (JWKS, PKCE S256) supporting machine discovery (`mcp:service`) and user-consented execution (`mcp:tools`).
- **Ambient Voice & Agent Actions**: Mai can ask *"Alexa, who is at the front door?"* or *"Alexa, tell them I am coming"* from anywhere in the home; Alexa+ calls AccessBell MCP tools to inspect the Gatekeeper claim and dispatch the quick reply.

## Why this is an AWS Builder project (Documented Integrations)

AccessBell features deep, documented integrations with core AWS services:

- **Amazon Bedrock**: Tier-2 grounded triage through LangChain `ChatBedrockConverse` and a structured `TriageResult` pydantic contract (default model `us.amazon.nova-2-lite-v1:0`). Detailed in `docs/ARCHITECTURE.md` §9 and `docs/AWS.md`.
- **Amazon EventBridge**: Outbound event bus (`backend/aws_events.py`) publishing triaged door events to custom buses for household automation.
- **Amazon Cognito**: OAuth 2.1 resource server for `/mcp` (`backend/oauth.py`) with two app clients (`accessbell-service` and `alexa-plus-mcp`).
- **Amazon ECS Fargate + Application Load Balancer**: Fully automated infrastructure as code (`infra/accessbell_stack.py`) with 300 s ALB idle timeout for SSE streaming.
- **Amazon RDS for PostgreSQL**: PostgreSQL 16 durable persistence with rolling-deploy lock safety (`backend/storage/postgres.py`).
- **AWS Secrets Manager**: Automated generation and injection of API tokens, MCP tokens, and webhook secrets.
- **Amazon SNS / SES**: Pluggable transports for consent-based escalation.

The deployment path is implemented and unit-tested at the adapter boundaries. A live demo instance
is deployed to ECS Fargate + RDS Postgres via CDK (see below); local evaluation and the video
recording run with the deterministic `stub` provider. See [AWS.md](AWS.md) for exactly what was
and was not run.

## How the judging criteria are addressed

| Criterion | Evidence |
|---|---|
| **Technical implementation** | Ring v1.1 HMAC ingest + signed in-app simulator; pydantic-validated LLM output; grounding demotion in code; Gatekeeper verification against resident context; durable at-most-once escalation; portable SQLite/Postgres; 427 collected tests (390 pass locally, 37 Postgres-skipped); 46-case gatekeeper/grounding eval with 46/46 passing |
| **Design** | TV-first PWA with large captions, urgency as text + color, 44 px targets, D-pad traversal, EN/VI bilingual mode, child mode, claim-specific headlines and challenges; pa11y WCAG2AA in CI |
| **Potential impact** | Built for a specific, underserved user (deaf/hard-of-hearing older adults living alone); addresses imposter scams with a measurable gate rather than a friendly guess; FTC 2024 data on imposter losses cited in the README |
| **Quality of the idea** | The differentiator is not another camera feed or captioning layer: it is **claim adjudication** against what the resident scheduled. The Gatekeeper is visible in the headline, not buried in settings |
| **Friction log bonus** | [FRICTION_LOG.md](FRICTION_LOG.md) records real API/documentation/simulator friction and the workarounds |

## Required product feedback

Every API, SDK, and tool used is covered in [PRODUCT_FEEDBACK.md](PRODUCT_FEEDBACK.md), including
Ring Partner API, Bedrock, CDK, ECS/Fargate, RDS, Cognito, EventBridge, SNS/SES, MCP, the Alexa+
MCP toolkit, and the browser/PWA surface.

## Live demo instance (AWS)

**http://Access-Acces-v4CzPoNSYUTf-590730701.us-east-1.elb.amazonaws.com** — the real CDK stack from
this repo, deployed in `us-east-1`: ECS Fargate behind an ALB, RDS Postgres 16, a Cognito user pool
with an OAuth 2.1 resource server, an EventBridge bus, and Secrets Manager tokens. The signed Ring
v1.1 simulator, the Gatekeeper, the MCP server, and the PWA are all live there. The task runs
`LLM_PROVIDER=bedrock` (the real `ChatBedrockConverse` path), but this account is not allowed to use
foundation models — every Converse call returns `Error 002: Access to Bedrock models is not allowed
for this account` — so the app fails open to Tier 1 + Gatekeeper captions and the UI states
*"Tier 2 model unavailable"* rather than pretending the model answered.
`scripts/check_bedrock_access.py` probes the account before a deploy so the failure is reported
instead of hidden. The instance is a **public demo**: the URL works as-is (no token), the write
endpoints are capped at 50 requests/minute per client IP, and the Ring webhook (HMAC) plus `/mcp`
(Cognito OAuth / `MCP_HTTP_TOKEN`) stay protected. The video does not print the ALB URL (the instance
may be scaled down after the demo window) — it says "Run the whole stack yourself:
`scripts/deploy_aws.sh`", so no dead link can appear on screen. Details and teardown:
[DEPLOYMENT.md](DEPLOYMENT.md) §3c.

## Demo video

A **2:47 narrated local cut** is prepared for upload, with English [captions](accessbell-demo.srt).
The cut is **English-only**; bilingual EN+VI is documented by the caption contract and UI strings.
It opens on an executive summary and an architecture card, then runs the flow end to end: a signed
Ring medicine delivery that arrives as a *grounded* caption with its evidence, the "I am a police
officer" claim that stays *Unverified* until the resident creates a matching patrol window in her own
door calendar, the bilingual EN + VI caption, the 10-foot TV presentation with the caption read
aloud, the talk panel (fixed prompts translate to Vietnamese, free text is refused rather than
mistranslated, the share brief stays locked behind consent), the escalation countdown that she stops
with one button — the stop written to the audit log before anything is sent — and the in-app
**Alexa+ MCP client (simulated)** panel running the same MCP tools as Alexa+: `initialize`, 11
tools, `get_door_alerts`, and `send_quick_reply`. It closes on an evidence slide (measured latency,
46/46 eval, grounding ablation), an honesty slide (what actually ran, what did not), and an end card
with the one-command run. Every hard cut sits inside the silence gap between narration cues. It uses
the signed Ring v1.1 simulator, the stub triage provider, and no physical Ring, Fire TV, or Alexa+
device. The public video URL is the remaining submission task; the README carries a
`TODO(submission)` placeholder until it is uploaded.

Suggested title: **AccessBell — the doorbell that checks the claim, not just the camera**.

Suggested description (copy/paste):

> AccessBell turns a Ring door event into accessible text on the screen the resident already owns.
> This 2:47 demo opens with an executive summary and an architecture card, then uses a signed
> Ring Partner API v1.1 simulator, a Gatekeeper that verifies claims
> only against resident-created windows, EN/VI TTS-safe captions, an escalation countdown the
> resident cancels with one button, and MCP tools for Alexa+. The last
> segment shows an in-app Alexa+ MCP client simulator calling the real endpoint; no physical device
> is used. The recording uses the deterministic stub provider; no physical Ring, Fire TV, or live
> AWS resource is shown. Code and evidence: https://github.com/duynguyendang/aws-access-bell
>
> #Accessibility #Ring #AWS #MCP #AmazonAppDev2026

To finish: upload the local cut (or a re-record with your own voice) to YouTube or Vimeo as public or
unlisted-but-viewable, replace the `TODO(submission)` in `README.md` with the URL, then run
`SUBMISSION_STRICT=1 python scripts/check_docs_consistency.py`.

## Submission checklist

- [x] Public GitHub repository with MIT license
- [x] README with setup, architecture, and evidence
- [x] Ring runtime path + signed simulator
- [x] AWS Builder path (Bedrock, CDK, EventBridge, Cognito, SNS/SES)
- [x] MCP server for Alexa+ (11 tools)
- [x] Product feedback for every API/SDK/tool used
- [x] Friction log
- [x] Narrated 2:47 local cut with SRT captions (`docs/accessbell-demo.srt`)
- [ ] Upload the <3-minute public video and replace `TODO(submission)` in `README.md`
- [ ] Select **Ring track** and **AWS Builder mini challenge** in the Devpost form
- [ ] Paste the repository URL and video URL into the submission form

## Known limitations (stated, not hidden)

- No physical Ring doorbell or Fire TV was available. The Ring v1.1 simulator and the PWA/TV layout
  were used; the hardware path is documented but not recorded.
- Fire TV is a **surface**, not the submitted track. The UI is TV-first and D-pad navigable, but it
  is a web app, not a packaged Fire TV app.
- The `visitor_statement` transcript is a demo extension, not a Ring webhook field.
- The AWS demo deployment may be scaled down after the judging window for cost reasons; the CDK path,
  live ALB URL, and adapter tests are documented in the repository.
- The bilingual UI was reviewed with automated tests and VI copy review, not a certified human
  translator or a full screen-reader audit. See [ACCESSIBILITY.md](ACCESSIBILITY.md).
