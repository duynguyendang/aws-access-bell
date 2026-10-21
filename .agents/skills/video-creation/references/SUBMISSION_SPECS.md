# Submission Video Specifications

## Target Constraints
- **Maximum Duration**: 3 minutes (180.0 seconds). Submissions exceeding this limit face penalties or disqualification.
- **Recommended Duration**: 2 minutes 30 seconds to 2 minutes 50 seconds.
- **Resolution**: 1920x1080 (1080p, 16:9 aspect ratio) or 1600x900.
- **Video Format**: MP4 (H.264 / AVC).
- **Audio Format**: Stereo AAC (128 kbps to 192 kbps, 44.1 kHz or 48 kHz).
- **Framerate**: 30 fps or 60 fps.

## Content Checklist (Hackathon Criteria)
- [ ] **Problem & Solution Pitch** (0:00 - 0:25): Accessibility barrier for Deaf and hard-of-hearing residents; visual-first door intelligence.
- [ ] **Architecture & Alexa+ Preview** (0:25 - 0:45): Self-hosted MCP Server (Streamable HTTP, JSON-RPC 2.0, spec 2025-11-25+), Alexa+ tool integration.
- [ ] **AWS Services Foundation** (0:45 - 1:00): Bedrock Converse (Claude 3.5 Sonnet / Haiku), EventBridge event bus, Cognito OAuth 2.1, ECS Fargate, RDS PostgreSQL.
- [ ] **Live Interactive Demos** (1:00 - 2:05):
  - Ring webhook ingestion & Tier 1/2 triage.
  - Bilingual captions (EN + VI) rendered on TV UI.
  - Alexa+ agent calling MCP tools (`list_recent_events`, `approve_action`, `escalate_event`).
  - Consent-gated escalation without face recognition.
- [ ] **Closing & Impact** (2:05 - 2:25): Inclusive ambient computing summary, GitHub repository, production readiness.
