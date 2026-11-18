# NorFigures: instructions for Claude and other agents

NorFigures verifies Norwegian economic figures (KPI, KPI-JAE, policy rate,
EUR/NOK) in ordinary text against SSB and Norges Bank. Full spec: `docs/spec.md`.

## The one rule

**The AI interprets, the source verifies.** A model may decide what a sentence
claims and which series answers it. It never supplies a number. Every
`official_value` must come from a fetch response in the same run.

## Where things live

- `facts/ledger.md`: fixed facts, definitions, canonical series. The only
  place a series ID is written. Code parses its ```json series``` block.
  If a fact is missing, report it as missing; do not fill it from memory.
- `facts/phrases.md`: phrase tables (hedges, forecast verbs, measure phrases,
  indicator words). Code applies them after extraction and for mapping.
- `agents/*.md`: agent contracts. `extractor.md` is also the extractor's system
  prompt, so editing it changes model behaviour and invalidates recordings.
- `src/norfigures/agents/`: the extractor agent. `llm.py` is the only module that
  imports the Anthropic SDK. The model has no tools and never fetches data.
- `src/norfigures/mapper.py`: deterministic mapping, no model (B18).
- `src/norfigures/mcp_server.py`: read-only MCP tools over the fetch layer.
- `src/norfigures/net.py`: the only network code. Allowlist of two hosts, GET only.
- `src/norfigures/fetch.py`: the only path from a series ID to an official number.
- `src/norfigures/verifier.py`: deterministic comparison under D4 to D16, plus the
  provenance check. No model is ever involved here.
- `docs/decisions.md`: decisions made and still pending. Pending defaults in
  spec section 7 are Haakon's to decide; do not settle them in code silently.

## Working rules

- Standard library only in `src/`, except `src/norfigures/agents/` and
  `mcp_server.py`, which may use the `agents` extra (`anthropic`, `mcp`; D18).
  Ask before adding any other dependency.
- Tests: `python -m unittest` from the repo root. They run offline against
  `tests/recorded/`. Keep them passing before every commit.
- Refresh recordings only on purpose: `NORFIGURES_RECORD=1 python -m unittest`
  re-runs every test against the live APIs and saves the responses. Commit the
  new files in `tests/recorded/http/`. A new fixture case needs this once.
- Model outputs: `norfigures record-agents` runs the extractor live on every
  fixture text (needs ANTHROPIC_API_KEY) and saves to `tests/recorded/agents/`.
  Re-record after changing `agents/extractor.md`, `facts/phrases.md` or the model.
- Fixture cases live in `tests/cases/*.json` (text, claims, expected verdicts;
  optional `expected_e2e` where the full loop should differ).
  Keep 15 to 20 of them; bad-input files go in `tests/cases/bad_input/`.
- Real-world headlines live in `tests/headlines/*.json` (outlet, link, release
  date, headline, hand-extracted claims, expected verdicts). Quote headlines
  only, never article bodies. `record-agents` records these too.
- Never add a host to `ALLOWED_HOSTS` without a decision recorded in `docs/decisions.md`.
- Fail loudly. A claim that cannot be checked is reported by name, never dropped.
- Keep values as `Decimal` from the source's own text; precision matters for rounding.
- No third-party proprietary code, data or prompts in this repo. Only open data and our own work.
