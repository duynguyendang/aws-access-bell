---
name: video-creation
description: >-
  Create, script, narrate, and verify submission and demo videos.
  Use this skill whenever the user asks to record, re-record, generate narration,
  produce slides or visuals, sync subtitles, or verify video specs for hackathon and product demo submissions.
---

# Video Creation Skill

Automated workflow for creating, scripting, narrating, and verifying demo and submission videos.

## Core Capabilities

1. **Scripting & Timing**: Translate project architecture and use cases into tightly timed SRT subtitle tracks (under 3 minutes for hackathons).
2. **Narration Synthesis**: Generate TTS voiceovers using AWS Polly (`boto3`) or Edge-TTS from SRT subtitle scripts.
3. **Visual & Slide Direction**: Structure visual transitions across slide decks (`docs/slides/`), live UI simulators, and MCP tool interactions.
4. **Validation & Compliance**: Ensure output video meets hackathon limits (duration ≤ 3:00, 1080p, AAC/MP3 audio, clear audio balance).
5. **Asset Cleanliness**: Maintain repository discipline by isolating heavy binary media into `docs/internal/assets/`.

---

## Workflow Steps

### Step 1: Script & Cue Breakdown
- Review `docs/accessbell-demo.srt` or target cue script.
- Ensure key project themes are explicitly covered:
  - Alexa+ Self-Hosted MCP Server integration (spec 2025-11-25+, Streamable HTTP).
  - AWS cloud foundation (Bedrock Converse, EventBridge, Cognito OAuth 2.1, ECS Fargate, RDS Postgres).
  - Accessibility-first UX (Fire TV captions, D-pad navigation, bilingual EN/VI).
- Run `python .agents/skills/video-creation/scripts/build_demo_plan.py` to produce a frame-by-frame visual recording timeline.

### Step 2: Voiceover Narration
- Generate speech cues matching the exact timestamps of the SRT file:
  ```bash
  .venv/bin/python .agents/skills/video-creation/scripts/generate_narration.py --srt docs/accessbell-demo.srt --engine polly --output docs/internal/assets/narration.mp3
  ```
- If running offline or with edge-tts, use `--engine edge-tts`.

### Step 3: Screen & Slide Recording
- Open high-resolution slides (`docs/slides/executive-summary.html`, `docs/slides/architecture.html`) in a clean 1920x1080 viewport.
- Run live services for interactive captures:
  - Ring webhook simulator: `python scripts/simulate_event.py delivery`
  - Alexa+ MCP tool inspector: `.venv/bin/python -m backend.mcp_server`
  - Web UI: `http://localhost:8000/`

### Step 4: Video Verification & Muxing
- Verify candidate video files against submission criteria:
  ```bash
  .venv/bin/python .agents/skills/video-creation/scripts/verify_demo.py docs/internal/assets/accessbell-demo.mp4
  ```
- Output checks:
  - Resolution: 1920x1080 or 1600x900
  - Duration: ≤ 180 seconds (3 minutes)
  - Audio codec: AAC / MP3, synchronized with SRT cues
  - Clean repository status: video stays under `docs/internal/assets/`

---

## Reference Documents

- [Submission Specifications](./references/SUBMISSION_SPECS.md)
