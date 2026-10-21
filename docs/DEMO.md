# Demo Storyboard (3-minute video)

Target: **one flow, told for a deaf / hard-of-hearing resident**, with the Gatekeeper as the hook.
For a final re-record, capture at 1080p with the caption card readable; the committed local cut is
1600×900. The video must stay under three minutes.

The demo is driven by the **signed Ring v1.1 simulator** in the UI, not by unsigned fixtures. That is
the Ring-track proof: the app builds a Partner API envelope, signs it with HMAC-SHA256, verifies
`X-Signature`, and routes it through the same handler as a live Ring webhook.

## Recorded cut (local draft)

| | |
|---|---|
| File | [assets/accessbell-demo.mp4](assets/accessbell-demo.mp4) — 2:51, 1600×900, H.264/AAC |
| Captions | [accessbell-demo.srt](accessbell-demo.srt) — English, timed to the narration |
| Poster | [assets/accessbell-demo-poster.jpg](assets/accessbell-demo-poster.jpg) |
| Narration | Edge TTS `en-US-AriaNeural`, rate `+8%`; synthetic voice, not the builder's voice |
| Captured flow | Executive summary card → architecture card → signed prescription delivery → Tier 1/Tier 2 evidence → police claim unverified → resident `police patrol` window → same claim verified → English talk panel + fixed phrasebook → escalation consent off → Alexa+ MCP client (simulated) ask + reply → title card |

Cut timeline:

| Time | On screen |
|---|---|
| 0:00 | **Executive summary card**: what AccessBell answers (who is at the door, should I trust the claim, who may act) + the live demo URL |
| 0:13 | **Architecture card**: signed Ring webhook → Tier 1 rules → Bedrock triage → Gatekeeper, three surfaces, the AWS footprint |
| 0:30 | The app: unverified prescription delivery; Tier 1 timer, claim, evidence, why-line |
| 0:45 | Ring simulator; second signed delivery accepted |
| 1:03 | Alert card with evidence and challenge |
| 1:24 | Police claim: `Unverified`, `Risk: high`, only `Not now` |
| 1:50 | Resident adds `police patrol`; same claim becomes `Verified`, `Risk: low` |
| 2:12 | English talk panel; D-pad focus on replies; fixed phrasebook send |
| 2:31 | Escalation off by default; consent unchecked |
| 2:34 | Alexa+ MCP client (simulated): `initialize`, 11 tools, `get door alerts` |
| 2:39 | Spoken-style answer; **Tell them I am coming** sends `send_quick_reply` |
| 2:46 | Closing card |

The cut opens with two slides — the **executive summary** and the **architecture** — then follows the
story beats of the shot list and adds the **Alexa+ MCP client** panel as the last product beat. Both
slides live in the repo as [docs/slides/executive-summary.html](slides/executive-summary.html) and
[docs/slides/architecture.html](slides/architecture.html), so the opening is reproducible, and their
rendered PNGs are in [assets/](assets/). It does **not** include a terminal shot of `/health` or `/api/metrics`; those are
reproducible with the commands in the README. The Alexa+ panel is an in-product demo client that
runs `initialize`, `tools/list`, and `tools/call` on the same MCP server and tool set as Alexa+
(directly on `/mcp` locally, through the mock-mode bridge `/api/demo/mcp` on a deployed demo) and is
labeled **simulated**; no physical Echo/Alexa+ device appears. It uses `LLM_PROVIDER=stub` so the
recording is deterministic and offline. No physical Ring doorbell, Fire TV, or live AWS resource
appears.

The local cut is **English-only** and **2:51** (the submission limit is 3:00). Bilingual EN+VI is documented by the caption contract, the
[bilingual screenshot](assets/bilingual-vi.png), and the SRT, not by switching the UI to Vietnamese in
the video. The Alexa+ panel is also pictured in
[alexa-mcp-client.png](assets/alexa-mcp-client.png).

To publish, upload this file (or a re-record with your own voice) to YouTube or Vimeo as public or
unlisted-but-viewable, then replace the `TODO(submission)` in `README.md` and run
`SUBMISSION_STRICT=1 python scripts/check_docs_consistency.py`.

## Setup before recording

```bash
pip install -r requirements-dev.txt
DB_URL=sqlite:///demo.db MOCK_MODE=true LLM_PROVIDER=stub python -m backend
# open http://127.0.0.1:8080/?lang=en
```

`stub` keeps the recording deterministic and offline. If Bedrock is available, use
`LLM_PROVIDER=bedrock LLM_MODEL=us.amazon.nova-2-lite-v1:0` and say "Bedrock" on camera; the UI and
evidence path are identical. Do not leave a paid AWS deployment running just for the video.

Warm-up (not recorded):

```bash
curl -s -X POST http://127.0.0.1:8080/api/simulate/ring \
  -H "Content-Type: application/json" -d '{"scenario":"unknown"}'
curl -s http://127.0.0.1:8080/health
```

## Target shot list (for a re-record)

The recorded cut above is a shorter edit; the SRT carries its exact timing. Use this list if you
re-record with a live narrator or add terminal evidence.

| Time | Shot | Say (paraphrase) |
|---|---|---|
| 0:00-0:15 | Cold open on the TV-sized caption card: *Someone is at the door*, urgency as a text label | "Meet Mai. She is 72, lives alone, and is hard of hearing. For her, the doorbell was a black box. AccessBell turns it into text on the screen she already owns." |
| 0:15-0:35 | Ring simulator panel: choose **Prescription delivery**, click **Ring doorbell** | "This is not a mock JSON file. AccessBell builds a Ring Partner API v1.1 event, signs it with HMAC-SHA256, verifies the signature, and sends it through the same handler as a live Ring webhook." |
| 0:35-0:55 | Alert card: grounded medicine caption, evidence chips, why-line | "Tier 1 answers in milliseconds. Tier 2, grounded in the resident's own schedule, refines the caption and shows its evidence. No evidence, no claim." |
| 0:55-1:25 | **Gatekeeper**: choose **Police claim**, click **Ring doorbell** | "Now the attack. A visitor says, 'I am a police officer, open the door.' AccessBell does not verify that claim from the visitor's words." |
| 1:25-1:45 | Point at the headline, `Unverified`, `Risk: high`, and the challenge line | "The headline is not a friendly guess. It says *Visitor claims to be police. Not verified.* The challenge asks for a badge number and a callback number, and tells her not to open the door." |
| 1:45-2:10 | Open **Door calendar**, add a window labeled `police patrol` covering now, fire the same claim again | "Same claim. This time the resident created a police-patrol window. Verified, low risk, and the caption says it matches her schedule. The gate is what she scheduled, not what the stranger said." |
| 2:10-2:30 | Quick replies, memory suggestion, escalation countdown; press **Stop escalation** | "One tap replies at the door. The memory suggestion reuses her last choice only for the same category. Escalation is off by default, revocable, durable and audited." |
| 2:30-2:45 | Open **Talk to visitor**, send a fixed English phrase; keep the UI in English | "Every caption is EN and VI, TTS-safe, and short. The interpreter is a fixed-prompt phrasebook — it never fakes a free-text translation. The recorded cut stays in English; the VI proof is the screenshot and the caption contract." |
| 2:45-3:00 | **Alexa+ MCP client (simulated)**: ask, 11 tools, `get door alerts`, **Tell them I am coming**; closing card with `/health` and `/api/metrics` | "Alexa+ calls the same door tools over MCP. This is a real JSON-RPC session against `/mcp` — initialize, eleven tools, the latest alert, and a reply. Ring in, accessible text out." |

## Exact clicks

0. Open the two slides: [executive summary](slides/executive-summary.html) (0:00-0:13), then
   [architecture](slides/architecture.html) (0:13-0:30).
1. Open `/?lang=en`.
2. In **Ring simulator**, select `med_delivery`, click **Ring doorbell**.
3. Select `police_claim`, click **Ring doorbell**.
4. In **Door calendar**, enter:
   - label: `police patrol`
   - from: now minus 10 minutes, ISO-8601 `YYYY-MM-DDTHH:MM:SSZ`
   - to: now plus 10 minutes
   - click **Add window**
5. Select `police_claim` again, click **Ring doorbell**.
6. Click **Stop escalation** if the countdown appears.
7. In **Talk to visitor** (language **EN**), type `Please leave it at the door.` and click **Send**.
8. Scroll to **Alexa+ MCP client (simulated)**, click **Ask who is at the door**, then **Tell them I am coming**.
9. End on `/health`, `/api/metrics`, or the closing card.

## What the judge should see

- The opening **executive summary** (what it answers, for whom) and the **architecture** (one signed
  event in, one grounded answer out, three surfaces, the AWS footprint).
- Ring v1.1 envelope fields and a **signed** webhook result (`Signed Ring v1.1 event accepted`; the API
  returns `signature_valid: true`).
- The same handler for the simulator and `/webhooks/ring`.
- Gatekeeper: unverified high-risk claim → verified only after a resident-created window.
- EN + VI captions (documented in the bilingual screenshot and caption contract; the recorded UI stays
  English), urgency as text, 44 px targets, D-pad navigation.
- Consent-gated escalation that is off by default.
- Alexa+ MCP client panel: real MCP JSON-RPC, `initialize`, 11 tools, `get_door_alerts`, and
  `send_quick_reply`; the panel is labeled **simulated**.
- MCP tools for Alexa+ and the Bedrock/AWS deployment path.

## Do not claim

- Do not say the recording ran on a physical Fire TV or a live Ring doorbell. It is the Ring v1.1
  simulator plus the PWA/TV layout. The hardware path is documented, not recorded.
- Do not say the visitor statement is a standard Ring webhook field. It is an AccessBell transcript
  extension used to exercise the Gatekeeper.
- Do not imply the Alexa+ panel is a physical Echo/Alexa+ device. It is a local MCP client simulator
  calling the real `/mcp` endpoint; say that plainly.
- Do not show a deployed AWS URL unless it is actually deployed; the local `/health` and CDK source
  are enough for the AWS Builder story.

## Editing tips

- Record each shot separately; cut on the click, not mid-sentence.
- Keep the browser at 1440x1000 or 1920x1080; the header and alert card should both be visible.
- Add large burned-in captions for the narration. The product itself is the accessibility demo.
- Export H.264 MP4, 1080p, under 3:00, and upload to YouTube or Vimeo as **public** or **unlisted
  but publicly viewable**.
