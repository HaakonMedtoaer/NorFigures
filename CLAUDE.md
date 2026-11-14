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
- `agents/*.md`: one contract per agent (extractor, mapper, explainer).
  Stay inside your contract's "Must not" list.
- `src/norfigures/net.py`: the only network code. Allowlist of two hosts, GET only.
- `src/norfigures/fetch.py`: the only path from a series ID to an official number.
- `docs/decisions.md`: decisions made and still pending. Pending defaults in
  spec section 7 are Haakon's to decide; do not settle them in code silently.

## Working rules

- Standard library only in `src/`. Ask before adding any dependency.
- Tests: `python -m unittest` from the repo root. They run offline against
  `tests/recorded/`. Keep them passing before every commit.
- Refresh recordings only on purpose: `NORFIGURES_RECORD=1 python -m norfigures latest`
  (with `PYTHONPATH=src` if not installed). Commit the new files in `tests/recorded/http/`.
- Never add a host to `ALLOWED_HOSTS` without a decision recorded in `docs/decisions.md`.
- Fail loudly. A claim that cannot be checked is reported by name, never dropped.
- Keep values as `Decimal` from the source's own text; precision matters for rounding.
- No third-party proprietary code, data or prompts in this repo. Only open data and our own work.
