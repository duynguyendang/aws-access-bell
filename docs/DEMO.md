# Demo Storyboard (3-minute video)

Target: **one flow, told for a deaf / hard-of-hearing resident**, with the Gatekeeper moment as the
hook. Record at 1080p; show the UI full-screen (Fire TV layout) and keep the caption panel readable.

## Setup before recording

```bash
pip install -r requirements-dev.txt -r requirements-bedrock.txt
AWS_REGION=us-east-1 LLM_PROVIDER=bedrock LLM_MODEL=us.amazon.nova-lite-v1:0 \
  DB_URL=sqlite:///demo.db MOCK_MODE=true python -m backend
# second terminal, once the app is up:
curl -X POST "http://127.0.0.1:8080/api/simulate?fixture=doorbell_unknown"   # warm-up, not shown
curl -s http://127.0.0.1:8080/health                                         # provider + model id
```

Bedrock is the product path for the recording: `LLM_PROVIDER=bedrock` needs an AWS account with the
model enabled (Nova Lite by default; `LLM_MODEL` overrides). `MOCK_MODE=true` only swaps the Ring
input for fixtures — it does not force the stub LLM. Fallback if Bedrock is unavailable: the `stub`
provider keeps the demo deterministic; if you record with it, say "offline test mode" on camera.

## Shot list

| Time | Shot | Say (paraphrase) |
|---|---|---|
| 0:00-0:20 | Cold open on the TV caption: *Someone is at the door* + urgency label | "Meet Mai — 72, lives alone, hard of hearing. For her the doorbell was a black box. AccessBell turns it into text — on the TV, on the phone, and in Alexa." |
| 0:20-0:45 | `POST /api/simulate?fixture=doorbell_med`; caption switches to the grounded med-delivery line with "Evidence" list | "Tier 1 answers instantly; Tier 2, grounded in the door calendar, refines it — and shows its evidence. No evidence, no claim." |
| 0:45-1:20 | **Gatekeeper**: `curl -X POST "http://127.0.0.1:8080/api/simulate?fixture=doorbell_police_claim"` | "A visitor claiming to be police. AccessBell will not verify a claim from the visitor's own words. Unverified — high risk — with a challenge question." |
| 1:20-1:40 | Add an expected window via the calendar form, replay the same claim | "Same claim, now with a window the resident created. Verified, low risk. The gate is evidence, not vibes." |
| 1:40-2:10 | Quick replies + Memory suggestion + escalation countdown, then Stop escalation | "One tap replies at the door. The memory suggestion reuses the last reply. Escalation is off until the resident turns it on — and it is revocable and audited." |
| 2:10-2:30 | Door talk interpreter: type a fixed visitor phrase, show EN/VI pair; switch `?lang=vi` | "Fixed phrases, EN and VI, no free-text translation — every caption is TTS-safe and bilingual." |
| 2:30-2:50 | Alexa+ / MCP: `curl` `tools/list` then one `tools/call` (`get_door_alerts`) | "Alexa+ joins over MCP: door intelligence as tools any agent can call." |
| 2:50-3:00 | Closing card + terminal on screen: `curl /health` (provider + model id) and `curl /api/metrics` (tier1/enrich p95 + grounding tally) | "Ring in, accessible text out. Rules answer in milliseconds, Bedrock grounds the caption with evidence. Privacy-first, runs today." |

## Tips

- Keep the browser zoom at 150% so captions are readable in the video.
- Use `?lang=vi` for one shot only; mention the bilingual toggle instead of showing both.
- Call the provider and model id out on screen (the `/health` shot); say that Tier 1 rules answer
  instantly and the model refines the caption with evidence.
- Re-record individual shots; do not do it in one take.
