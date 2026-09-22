# AGENTS.md

Conventions and rules for working in this repository. Read this before changing code or docs.

## Project

AccessBell — accessibility-first door intelligence. Ring webhook → Tier 1 rules → Tier 2 LLM
(LangChain) → accessible surfaces (Fire TV caption, Alexa+ MCP tools, PWA). Python/FastAPI;
SQLite or Postgres; MCP server for Alexa+; no face recognition, consent-gated escalation.

## Commands

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt   # once
.venv/bin/python -m pytest -q                                            # full suite (SQLite)
.venv/bin/python -m pytest tests/test_triage_data.py -k pharmacy -q      # single test / case
TEST_POSTGRES_DSN=postgresql://user:pw@host/db .venv/bin/python -m pytest -q   # + Postgres
.venv/bin/python -m backend                # run server (honors PORT), or uvicorn backend.main:app
scripts/smoke_docker.sh [image]            # container smoke test
scripts/deploy_cloudrun.sh <project> [region]   # GCP Cloud Run deploy
```

## Language rules

1. **English everywhere in code**: identifiers, comments, commit messages, tests, scripts, docs, README.
   Exception: `docs/internal/` may be written in Vietnamese — it is local-only and never published.
2. **Vietnamese is product data, never code.** All user-facing VI strings live in exactly one place:
   `backend/captions.py`.
3. Never inline a caption or brief bullet in logic — add it to `backend/captions.py` with both `en`
   and `vi`, then call `captions.stub_captions()`, `captions.generic_captions()` or `captions.render()`.
4. `prompts/triage.txt` may contain VI sample output (it is prompt data, not UI copy).
5. Docs stay English. If a doc shows VI output, mark it as sample data.
6. Every caption must be: non-empty in **both** languages, **TTS-safe** (no emoji/symbols), and
   ≤ `captions.MAX_CAPTION_LENGTH`. `tests/test_captions.py` enforces this — run it when touching strings.

## Code conventions

- **No comments** in code unless explicitly requested; prefer clear names and tests.
- LLM output never reaches a user directly: it must pass `TriageResult` validation and the
  `EnrichmentPipeline` grounding rule (a specific category without evidence is demoted to the generic
  caption). Do not bypass or weaken this.
- New evidence source → add it to `KNOWN_EVIDENCE_SOURCES`, `prompts/triage.txt`, the triage test
  data, and the docs.
- SQL must stay portable across dialects:
  - use `?` placeholders (the Postgres dialect translates them);
  - never `SELECT DISTINCT … ORDER BY <column not in the select list>` (invalid on Postgres) —
    dedupe in Python instead (this bug already happened once);
  - no SQLite-only SQL (`PRAGMA`, `datetime('now')`) outside `backend/storage/`;
  - a new table or column must be added to **both** `backend/schema.sqlite.sql` and
    `backend/schema.postgres.sql`.
- Escalation must remain durable: persist `escalation_pending` **before** scheduling, and fire through
  `claim_pending_escalation()` (a single conditional DELETE) for at-most-once delivery.
- Keep process state disposable: anything that must survive a restart belongs in the database.
- Secrets are never logged or committed; `.env` stays out of git.

## Accessibility acceptance (must hold)

- Captions: EN + VI, TTS-safe, short; urgency always carries a **text** label, never color alone.
- Reply targets ≥ 44 px; TV-remote (D-pad) navigation reaches every action.
- Escalation and sharing default to **OFF**, are revocable, and are audited; no face embeddings, ever.
- Any new user-visible string needs a `backend/captions.py` entry and a passing `test_captions`.

## Change checklist (keep docs in sync)

| Change | Also update |
|---|---|
| New env var | `.env.example`, README env table, `docs/DEPLOYMENT.md` config table |
| New MCP tool | README tool table, `EXPECTED_TOOLS` in `tests/test_mcp_server.py`, `docs/ARCHITECTURE.md` tool catalog |
| New API route | `tests/test_api.py`, `docs/ARCHITECTURE.md` HTTP API table |
| New table/column | both schema files, `docs/ARCHITECTURE.md` data model |
| New/changed caption | `backend/captions.py` + `tests/test_captions.py` |
| Test count changes | README, `docs/ARCHITECTURE.md` §14, `docs/internal/STORY.md`, `docs/internal/PORTABILITY_PLAN.md` §0 |
| New doc | published → `docs/` (English) + README repo layout + Links table; internal → `docs/internal/` |
| New deploy target | `docs/DEPLOYMENT.md` targets matrix |

## Publishing rules

- `docs/internal/` holds strategy and planning notes (story, use cases, competition, portability
  plan, business flow). It is **gitignored** and must never be linked from published docs.
- Public docs are `README.md`, `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT.md`, plus the
  code, schemas, prompts, web UI and tests.
- Before publishing, confirm no secret or private note leaks into tracked files:
  `git status --porcelain` must not list anything under `docs/internal/`.

## Definition of done

- `pytest -q` green on SQLite; the Postgres run is green when `TEST_POSTGRES_DSN` is available.
- No Vietnamese anywhere except `backend/captions.py`, `prompts/triage.txt`, assertions in tests that
  verify VI output, and local-only notes under `docs/internal/`.
- Docs updated per the checklist above; docs remain English-only.