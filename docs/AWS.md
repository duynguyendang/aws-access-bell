# AccessBell on AWS (Builder mini challenge notes)

This document is the AWS-specific evidence for the submission. It separates **what is wired and
synth-tested** from **what was actually run in this environment**, so judges can verify claims
without a paid deployment.

## 1. AWS services used

| Service | Role in AccessBell | Where |
|---|---|---|
| **Amazon Bedrock** | Tier-2 grounded triage through LangChain `ChatBedrockConverse`; default model `us.amazon.nova-2-lite-v1:0` | `backend/llm/factory.py`, `docs/ARCHITECTURE.md` §9 |
| **AWS CDK (Python)** | Infrastructure as code for the whole stack | `infra/accessbell_stack.py`, `infra/app.py` |
| **Amazon ECS Fargate** | Runs the FastAPI container; 0.25 vCPU / 0.5 GB, desired count 1 | `infra/accessbell_stack.py` |
| **Application Load Balancer** | Public entry point; 300 s idle timeout for SSE; optional HTTPS listener | `infra/accessbell_stack.py` |
| **Amazon RDS for PostgreSQL** | Durable events, labels, expected windows, escalation timers, audits | `infra/accessbell_stack.py`, `backend/storage/postgres.py` |
| **Amazon Cognito** | OAuth 2.1 resource server for `/mcp`; service client + optional Alexa+ auth-code client | `infra/accessbell_stack.py`, `backend/oauth.py` |
| **Amazon EventBridge** | Optional custom bus for every triaged event (`EVENTBRIDGE_BUS_NAME`; empty = off) | `backend/aws_events.py` |
| **AWS Secrets Manager** | Generates API token, MCP token, Ring webhook secret, DB password | `infra/accessbell_stack.py` |
| **Amazon SNS / SES** | Optional escalation and announce transports | `backend/notifier.py` |
| **Amazon CloudWatch Logs** | Container logs, 1-week retention | `infra/accessbell_stack.py` |

## 2. What was validated here

- `cdk synth` succeeds with the default context and with
  `-c certificate_arn=... -c alexa_callback_urls=...` (two Cognito clients, HTTPS listener,
  HTTP-to-HTTPS redirect).
- The Bedrock adapter is covered by provider-factory tests; the live Bedrock call was not made in
  this environment because no paid deployment/model invocation was left running.
- The Postgres storage dialect is covered when `TEST_POSTGRES_DSN` is set; the local suite runs
  SQLite by default (37 Postgres variants skipped without a DSN).
- The local demo uses `LLM_PROVIDER=stub` for deterministic screenshots and tests. The AWS CDK stack
  sets `LLM_PROVIDER=bedrock` by default.

**Not claimed:** this submission was not deployed to a live AWS account, and no public AWS URL is
presented as working. The CDK path is source-verified and synth-tested, not production-run.

## 3. Deploy

Prerequisites: AWS CLI, CDK CLI, Docker, an AWS account with Bedrock model access for the chosen
model, and (for Ring) an ACM certificate for a domain you control.

```bash
# Optional but required for a real Ring callback:
export CERTIFICATE_ARN=arn:aws:acm:us-east-1:123456789012:certificate/...
export ALEXA_CALLBACK_URLS=https://your-alexa-callback.example

./scripts/deploy_aws.sh us-east-1
```

The script loads `aws.env` if present (gitignored), verifies credentials with
`aws sts get-caller-identity`, bootstraps CDK if needed, and deploys with
`--require-approval never`.

Outputs include:

- `ServiceUrl` and `RingWebhookUrl` (HTTPS when `CERTIFICATE_ARN` is set, otherwise HTTP)
- `HttpsEnabled`
- `UserPoolId`, `CognitoClientId` (service client), `AlexaClientId` (or `not-configured`)
- `JwksUrl`, `EventBusName`
- `ApiTokenSecretArn`, `McpTokenSecretArn`, `RingWebhookSecretArn`

Read a generated token:

```bash
aws secretsmanager get-secret-value \
  --secret-id <ApiTokenSecretArn> --query SecretString --output text
```

Then point the Ring app callback at `RingWebhookUrl` and copy the webhook secret into the Ring
developer console. Ring requires HTTPS; use `CERTIFICATE_ARN` and a DNS record for the ALB.

## 4. HTTPS and Alexa+ OAuth details

- Without `CERTIFICATE_ARN`, the ALB exposes HTTP only. That is suitable for a quick smoke test but
  **not** for Ring, which requires an HTTPS callback.
- With `CERTIFICATE_ARN`, the stack creates an HTTPS listener and redirects HTTP to HTTPS.
- Cognito does not allow `client_credentials` and authorization-code grant on the same app client,
  so the stack creates:
  - `accessbell-service` — `client_credentials`, scope `accessbell/mcp:service` (discovery/ping only)
  - `alexa-plus-mcp` — authorization-code grant, scopes `accessbell/mcp:tools` and
    `accessbell/mcp:resources`, only when `ALEXA_CALLBACK_URLS` is set
- Both client IDs are passed to the app as `OAUTH_CLIENT_IDS`.

For Alexa+, set `MCP_401_WWW_AUTHENTICATE=false` (the Alexa+ MCP client does not yet support the
`WWW-Authenticate` discovery header). See `.env.example` and `docs/ARCHITECTURE.md` §12.

## 5. Cost and cleanup

Rough always-on estimate for the default stack (us-east-1, no free tier), **not a quote**:

| Item | Approx. monthly |
|---|---|
| RDS `db.t4g.micro`, 20 GB gp3 | $15–20 |
| Fargate 0.25 vCPU / 0.5 GB | $8–12 |
| ALB + minimal LCU | $18–25 |
| Secrets Manager (4 secrets) | ~$2 |
| CloudWatch Logs, EventBridge | < $2 |
| ACM certificate | free for public certs used with ALB |
| **Total** | **~$45–60** |

Bedrock is pay-per-token and only used on enriched events. To stop charges:

```bash
cd infra
cdk destroy
```

RDS and the ALB are the main cost drivers. The stack sets `RemovalPolicy.DESTROY` for the demo
database and user pool; do not use that setting for resident data without changing it first.

## 6. Security notes

- Secrets are generated in Secrets Manager; no default token is committed.
- RDS is in private isolated subnets; only the ECS security group can reach port 5432.
- The Fargate task has a public IP for image pulls/outbound calls but no inbound rule except the ALB.
- `/webhooks/ring` verifies HMAC; `/api/*` requires `API_TOKEN` when `API_AUTH_DISABLED=false`;
  `/mcp` requires OAuth/JWT or the demo token.
- The container runs with `APP_ENV=production`, so the startup assertions reject an empty
  `API_TOKEN`.
- EventBridge publishing is fail-open: a bus failure never blocks a door alert.

## 7. AWS Builder mini challenge mapping

| Mini-challenge expectation | AccessBell evidence |
|---|---|
| Uses AWS services meaningfully | Bedrock triage, ECS Fargate runtime, RDS persistence, Cognito OAuth, EventBridge events, Secrets Manager |
| Infrastructure as code | `infra/` CDK stack; `cdk synth` passes |
| Deployable path | `scripts/deploy_aws.sh`, Dockerfile, Postgres schema, health check |
| Security | private RDS, generated secrets, HMAC, OAuth scopes, production assertions |
| Cost awareness | scale-to-zero is safe for escalation; one Fargate task; destroy path documented |
| Honest scope | local stub for the demo; no live AWS URL claimed |
