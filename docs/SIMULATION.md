# AccessBell Simulation Guide

This guide describes how to simulate, test, and validate AccessBell across Fire TV, Alexa+, Ring, and AWS Bedrock without requiring physical hardware.

---

## 1. Simulation Pyramid

```
                ┌───────────────────────────────────┐
                │ Level 3: Physical Devices         │
                │ Real Ring, Fire TV Stick, Echo    │
                ├───────────────────────────────────┤
                │ Level 2: Cloud Staging Simulators │
                │ AWS ECS + Cognito + Alexa Console │
                ├───────────────────────────────────┤
                │ Level 1: Protocol & Signed Replay │
                │ scripts/ring_replay.py + MCP curl │
                ├───────────────────────────────────┤
                │ Level 0: Local Mock & In-Memory   │
                │ PWA + /api/simulate + Stub LLM    │
                └───────────────────────────────────┘
```

| Level | Hardware | Cloud Credentials | Primary Use Case |
|---|---|---|---|
| **Level 0** | None | None | Instant local dev, UI review, unit tests, fast feedback |
| **Level 1** | None | None | Ring HMAC signature validation, MCP JSON-RPC compliance |
| **Level 2** | None | AWS Account | Alexa+ developer console, Cognito OAuth 2.1, Bedrock LLM |
| **Level 3** | Ring + Fire TV + Echo | AWS + Amazon Developer | Final acceptance, live doorbell push, ambient audio |

---

## 2. Level 0: Local Mock & In-Memory

Run AccessBell completely locally with zero cloud dependencies.

### Step 2.1: Start the Local Server

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m backend
```

The server listens on `http://localhost:8080`.

### Step 2.2: Launch the Fire TV / PWA Interface

Open your browser to:
- English: `http://localhost:8080/?lang=en`
- Vietnamese: `http://localhost:8080/?lang=vi`

#### Fire TV D-Pad Remote Simulation
The web interface includes built-in TV remote navigation:
- `Arrow Keys` (`Up`, `Down`, `Left`, `Right`): Navigate focus between quick-reply targets. While a
  text input is focused, Left/Right keep the caret and Up/Down still navigate.
- `Enter` / `Space`: Select highlighted action (`leave_at_door`, `coming`, `not_now`, `waiting_for_parent`).
- Visual indicator: Active element displays a high-contrast focus outline conforming to TV accessibility guidelines (minimum target size ≥ 44px).

### Step 2.3: Trigger Simulated Doorbell Events

Use the simulation chips in the bottom toolbar or send HTTP requests:

```bash
# Pharmacy / Medication delivery
curl -X POST "http://localhost:8080/api/simulate?fixture=doorbell_med"

# Package with delivery expectation window
curl -X POST "http://localhost:8080/api/simulate?fixture=doorbell_package_window"

# Unknown visitor
curl -X POST "http://localhost:8080/api/simulate?fixture=doorbell_unknown"

# Visitor claiming to be police (Gatekeeper demo: unverified + challenge question)
curl -X POST "http://localhost:8080/api/simulate?fixture=doorbell_police_claim"

# Night motion
curl -X POST "http://localhost:8080/api/simulate?fixture=motion_night"
```

The Fire TV screen immediately renders the Tier 1 raw caption in <200 ms, followed by the enriched Tier 2 card once triage completes.

### Step 2.4: Fire the signed Ring v1.1 simulator

The UI includes a **Ring simulator** panel. It builds a Ring Partner API v1.1 envelope, signs it
with HMAC-SHA256, verifies `X-Signature`, and hands it to the same `RingWebhookHandler` used by the
live `/webhooks/ring` endpoint. No Ring device or account is required.

```bash
# List demo scenarios
curl -s http://localhost:8080/api/simulate/ring/scenarios

# Fire a police-claim scenario (unverified Gatekeeper demo)
curl -s -X POST http://localhost:8080/api/simulate/ring \
  -H "Content-Type: application/json" \
  -d '{"scenario":"police_claim"}'

# Override the simulated visitor statement
curl -s -X POST http://localhost:8080/api/simulate/ring \
  -H "Content-Type: application/json" \
  -d '{"scenario":"package","visitor_statement":"I have a parcel for Mai."}'
```

The response includes `version: "1.1"`, `signature_valid: true`, the internal `event_id` and the
`ring_event_id`. The same event then appears over SSE and in `/api/events`.

**Honesty note:** `data.attributes.visitor_statement` is an AccessBell integration extension that
represents a door transcript. Real Ring v1.1 webhooks contain `meta` + `data.attributes.source` /
`source_type` / `timestamp`, not tags, label hints or a transcript. The simulator exists to exercise
the runtime path and the Gatekeeper without pretending those fields are part of the Ring API.

---

## 3. Level 1: Protocol & Signed Replay

Test real protocol flows without live Ring or Alexa accounts.

### Step 3.1: Replay Ring Webhooks with HMAC-SHA256

Simulate real webhook payloads signed with HMAC-SHA256:

```bash
# Replay all mock fixtures with 2-second delay
python3 scripts/ring_replay.py --url http://localhost:8080/webhooks/ring --secret "your-ring-secret" --delay 2

# Replay single fixture
python3 scripts/ring_replay.py --fixture doorbell_med --url http://localhost:8080/webhooks/ring --secret "your-ring-secret"
```

The replay tool sends:
- Header: `X-Signature: sha256=<hmac>`
- Content-Type: `application/json`
- Supports both Partner Envelope v1.1 and flat JSON payloads.

### Step 3.2: In-app Alexa+ MCP client (simulated)

With `MOCK_MODE=true`, the PWA includes an **Alexa+ MCP client (simulated)** panel. Click **Ask who
is at the door**: it runs `initialize`, `tools/list`, and `tools/call` on the same MCP server and
tool set as Alexa+ (directly on `/mcp` locally, through the mock-mode bridge `/api/demo/mcp` on a
deployed demo, because the browser never holds the MCP token); **Tell them I am coming** sends
`send_quick_reply`. The panel is labeled simulated and does not claim a physical Echo/Alexa+ device.

### Step 3.3: Inspect Live SSE Stream

Subscribe to the server-sent events stream in real time:

```bash
curl -N http://localhost:8080/api/stream
```

Example stream output:
```text
data: {"type": "alert_raw", "event_id": 1, "text": "Someone is at the door", "text_en": "Someone is at the door", "text_vi": "Có người ở cửa", "category": "UNKNOWN_VISITOR", "latency_ms": 2.1, "visitor_statement": "I am a police officer. Please open the door."}

data: {"type": "alert_enriched", "event_id": 1, "status": "enriched", "triage": {"category": "UNKNOWN_VISITOR", "urgency": 4, "caption_en": "Visitor claims to be police. Not verified.", "caption_vi": "Khách nói là công an. Chưa xác minh.", "grounding": "generic", "verification_status": "unverified", "risk_level": "high"}}
```

### Step 3.4: Test MCP Tools via JSON-RPC

Call AccessBell tools using `curl` with a bearer token:

```bash
# List available tools
curl -s http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-token" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'

# Query door status
curl -s http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-token" \
  -d '{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "get_door_status", "arguments": {}}}'
```

---

## 4. Level 2: Cloud Staging with Device Simulators

Test full cloud deployment on AWS with Alexa+ and Fire TV simulator tools.

### Step 4.1: Deploy to AWS via CDK

Deploy the automated ECS Fargate, RDS Postgres, Bedrock, and Cognito stack:

```bash
# Configure AWS CLI credentials
aws configure

# Run turnkey deployment
./scripts/deploy_aws.sh us-east-1
```

Note the CloudFormation outputs:
- `ServiceUrl`: `http://<alb-dns-name>`
- `UserPoolId`: `us-east-1_xxxxxxxxx`
- `CognitoClientId`: `xxxxxxxxxxxxxxxxxxxxxxxxxx`

### Step 4.2: Alexa+ Simulator Integration

1. In the **Amazon Developer Console** under Alexa+:
   - Register an MCP server pointing to: `https://<your-alb-dns-name>/mcp`
   - Select OAuth 2.1 authentication using the Cognito User Pool endpoint.
2. In the **Alexa Simulator / ASK CLI**:
   - Utterance: *"Alexa, who is at the front door?"*
   - Utterance: *"Alexa, tell them to leave the package at the door."*
   - Utterance: *"Alexa, summarize door visits today."*
3. The Alexa+ Agent routes utterances to `get_latest_door_event`, `send_quick_reply`, and `summarize_door_day`.

### Step 4.3: Fire TV Web App Simulator

To test the TV 10-foot experience:
1. Open Chrome or Chromium in Device Emulation mode.
2. Set viewport to `1920x1080` (1080p Full HD) or `1280x720` (720p HD).
3. Verify:
   - TV Safe Zone margins (no text clipped within 5% screen edge).
   - Text legibility from 10 feet (captions rendered at ≥ 28px).
   - High contrast ratio (WCAG AAA compliant colors).
   - Audio announcement triggers speech synthesis in selected language.

---

## 5. Level 3: Hardware Integration

When ready for physical hardware validation:

1. **Ring Video Doorbell:**
   - Configure Ring Developer Account webhook destination URL to `https://<your-domain>/webhooks/ring`.
   - Set secret in AccessBell: `RING_WEBHOOK_SECRET=<your-ring-secret>`.
2. **Amazon Fire TV:**
   - Package `web/` using Amazon Web App Starter Kit (WASK) or launch Silk Browser pointing to `https://<your-domain>/?token=<token>`.
   - Enable ambient captions overlay mode.
3. **Echo Show / Alexa+ Device:**
   - Link the Alexa Developer account to your physical Echo device.
   - Voice interactions invoke the cloud MCP tools deployed on AWS ECS.

---

## 6. Simulation Troubleshooting

| Issue | Cause | Resolution |
|---|---|---|
| `POST /api/simulate` returns 404 | `MOCK_MODE=false` in production | Set `MOCK_MODE=true` for testing, or use `/webhooks/ring` with signed payloads |
| `POST /api/simulate/ring` returns 404 | `MOCK_MODE=false` in production | Set `MOCK_MODE=true`; the simulator is deliberately demo-only |
| `POST /webhooks/ring` returns 401 | Invalid HMAC signature | Verify `RING_WEBHOOK_SECRET` matches signing key, or use `scripts/ring_replay.py --secret <key>` |
| MCP tool call returns 401 | Missing OAuth token or bearer token | Pass `Authorization: Bearer <token>` matching `MCP_HTTP_TOKEN` or Cognito JWT |
| SSE disconnects after 60 seconds | Load balancer idle timeout | Ensure ALB `idle_timeout.timeout_seconds` is set to 300 (configured in CDK stack) |
| Fire TV captions do not update | SSE connection dropped | Check browser console network tab for `/api/stream` reconnection attempts |
