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

## Why this is an AWS Builder project

- **Amazon Bedrock** is the product triage path (`LLM_PROVIDER=bedrock`, Nova Lite by default)
  through LangChain `ChatBedrockConverse` and a structured `TriageResult`.
- **AWS CDK** deploys ECS Fargate + ALB + RDS Postgres + Cognito + EventBridge + Secrets Manager
  (`infra/`, `scripts/deploy_aws.sh`).
- **Amazon EventBridge** publishes triaged events to a custom bus when `EVENTBRIDGE_BUS_NAME` is set.
- **Amazon Cognito** provides the OAuth 2.1 resource-server path for `/mcp`.
- **Amazon SNS / SES** are supported escalation/announce transports.
- **Amazon ECS Fargate + RDS Postgres** keep the service and data in the customer's own account.

The deployment path is implemented and unit-tested at the adapter boundaries. This submission was
validated locally with the deterministic `stub` provider; no paid AWS deployment was left running.
See [AWS.md](AWS.md) for exactly what was and was not run.

## How the judging criteria are addressed

| Criterion | Evidence |
|---|---|
| **Technical implementation** | Ring v1.1 HMAC ingest + signed in-app simulator; pydantic-validated LLM output; grounding demotion in code; Gatekeeper verification against resident context; durable at-most-once escalation; portable SQLite/Postgres; 423 collected tests (386 pass locally, 37 Postgres-skipped); 46-case gatekeeper/grounding eval with 46/46 passing |
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
v1.1 simulator, the Gatekeeper, the MCP server, and the PWA are all live there. The instance runs in
mock mode (so the in-app Ring simulator and the Alexa+ client panel are usable) with the
deterministic stub provider, because this account has no Amazon Bedrock model access; the CDK
default stays `LLM_PROVIDER=bedrock`; `scripts/check_bedrock_access.py` probes the account before a
deploy so the failure is reported instead of hidden. `/api/*` requires the API token — open the URL
once with `?token=<API_TOKEN>` and the browser keeps it. Details and teardown:
[DEPLOYMENT.md](DEPLOYMENT.md) §3c.

## Demo video

The recording plan and exact clicks are in [DEMO.md](DEMO.md). A **2:24 narrated local cut** is
available at [assets/accessbell-demo.mp4](assets/accessbell-demo.mp4), with English
[captions](accessbell-demo.srt). The cut is **English-only**; bilingual EN+VI is documented by the
[VI screenshot](assets/bilingual-vi.png) and the caption contract. The last product segment shows the
in-product **Alexa+ MCP client (simulated)** panel running the same MCP tools as Alexa+:
`initialize`, 11 tools, `get_door_alerts`, and `send_quick_reply`. It uses the signed Ring v1.1
simulator, the stub triage provider, and no physical Ring, Fire TV, Alexa+ device, or live AWS
resource. The public video URL is the remaining submission task; the README carries a
`TODO(submission)` placeholder until it is uploaded.

Suggested title: **AccessBell — the doorbell that checks the claim, not just the camera**.

Suggested description (copy/paste):

> AccessBell turns a Ring door event into accessible text on the screen the resident already owns.
> This 2:24 demo uses a signed Ring Partner API v1.1 simulator, a Gatekeeper that verifies claims
> only against resident-created windows, EN/VI TTS-safe captions, and MCP tools for Alexa+. The last
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
- [x] README with setup, architecture, evidence, and screenshots
- [x] Ring runtime path + signed simulator
- [x] AWS Builder path (Bedrock, CDK, EventBridge, Cognito, SNS/SES)
- [x] MCP server for Alexa+ (11 tools)
- [x] Product feedback for every API/SDK/tool used
- [x] Friction log
- [x] Narrated 2:24 local cut with SRT captions (`docs/assets/accessbell-demo.mp4`)
- [ ] Upload the <3-minute public video and replace `TODO(submission)` in `README.md`
- [ ] Select **Ring track** and **AWS Builder mini challenge** in the Devpost form
- [ ] Paste the repository URL and video URL into the submission form

## Known limitations (stated, not hidden)

- No physical Ring doorbell or Fire TV was available. The Ring v1.1 simulator and the PWA/TV layout
  were used; the hardware path is documented but not recorded.
- Fire TV is a **surface**, not the submitted track. The UI is TV-first and D-pad navigable, but it
  is a web app, not a packaged Fire TV app.
- The `visitor_statement` transcript is a demo extension, not a Ring webhook field.
- The AWS deployment was not left running for cost/account reasons; the CDK path and adapter tests
  are in the repository.
- The bilingual UI was reviewed with automated tests and VI copy review, not a certified human
  translator or a full screen-reader audit. See [ACCESSIBILITY.md](ACCESSIBILITY.md).
