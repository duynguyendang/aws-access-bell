# Accessibility Statement (web UI)

AccessBell targets **WCAG 2.2 AA** for its user surfaces: the Fire TV kiosk UI and the phone PWA.

## What is enforced automatically

| Area | Check | Where |
|---|---|---|
| WCAG2AA audit (axe/HTMLCS via pa11y) | `pa11y --standard WCAG2AA` on `/` and `/?lang=vi`, with a simulated enriched alert | CI job `a11y` |
| Caption text | EN + VI, non-empty, TTS-safe (no emoji/symbols), length cap | `tests/test_captions.py` |
| Caption wording | Urgency always carries a text label; color is never the only signal | `tests/test_captions.py` |
| Language coverage | `UI["en"]` and `UI["vi"]` key sets must match | `tests/test_captions.py` |

## Design guarantees in the UI

- **Reply targets** (quick replies, toggles, forms) have a minimum height of 44 px.
- **Focus is visible**: 4 px focus outline on buttons, inputs, selects and links.
- **D-pad navigation**: arrow keys move focus across all visible buttons and inputs. Arrow keys never
  hijack text editing: inside a single-line input, Left/Right keep the caret and Up/Down still
  navigate.
- **Captions are the primary channel**: every alert, why-line and reply label has an EN and VI variant
  served from a single phrasebook (`backend/captions.py`).
- **Escalation and sharing are OFF by default**, revocable, and audited. No face embeddings are used
  or stored, ever.

## Known gaps (not yet verified)

- Physical Fire TV / Vega OS run with the Amazon Web App Tester (planned; LAN + Fire TV steps are in
  `docs/SIMULATION.md`).
- Screen-reader pass with a human tester (VoiceOver / TalkBack / Fire TV VoiceView).
- Vietnamese content review by a native speaker (strings are in place; wording feedback pending).
- Latency of on-device TTS for long captions (Fire TV reading of the alert panel).

## Run the checks yourself

```bash
pip install -r requirements-dev.txt
DB_URL=sqlite:///a11y.db MOCK_MODE=true API_AUTH_DISABLED=true python -m uvicorn backend.main:app --port 8080 &
curl -X POST "http://127.0.0.1:8080/api/simulate?fixture=doorbell_med"
npx -y pa11y@9 --standard WCAG2AA http://127.0.0.1:8080/
npx -y pa11y@9 --standard WCAG2AA "http://127.0.0.1:8080/?lang=vi"
```
