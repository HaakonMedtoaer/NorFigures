# Decisions

Who decided, what, and why. Claude Code writes the code; Haakon makes the
calls listed here. Status is **decided** or **pending**.

## Decided

| # | Date | Decision | Why | By |
|---|---|---|---|---|
| D1 | 2026-11 | The AI interprets, the source verifies. No model ever supplies a number. | Core trust property of the tool. | Haakon |
| D2 | 2026-11 | Name NorFigures, MIT licence, English README with a Norwegian summary. | Spec section 16. | Haakon |
| D3 | 2026-11-14 | Exit codes 0 / 1 / 2 / 3 as in spec section 5; "nothing checked" exits 2. | A silent pass is the worst failure. | Haakon |
| D4 | 2026-11-14 | Ambiguous measure: when a claim has two valid readings (for example KPI vs KPI-JAE, or monthly vs 12-month change) and the text gives too little context to choose, show **both** official figures and explain in plain words what each one measures. Never pick one silently. | The reader knows the context better than the tool; showing both lets them see which figure they meant. | Haakon |
| D5 | 2026-11-14 | Verdict for D4 cases: `matched` with label `ambiguous_measure` if the stated value matches either reading; `mismatched` if it matches neither. The report always shows both figures and names which reading fits. | Exit code 1 stays reserved for a real error; CI does not fail over wording alone. | Haakon |

## Weekend 1 build choices (for review)

These were made while building the source layer. They are low-risk but Haakon
should confirm or overturn them.

| # | Choice | Why |
|---|---|---|
| B1 | All CPI series read from SSB table **14706** (KPI and KPI-JAE rows). | 14706 replaced the closed tables 05327/03013 at the 2026 rebase (2025=100). One table means one query shape. Its KPI row should equal the headline in table 14700; a cross-check test can confirm. |
| B2 | Policy rate is Norges Bank `IR/B.KPRA.SD.R`, business-daily. The rate in force on a date is the last observation on or before it. | Matches the ledger definition; handles weekends and holidays. |
| B3 | EUR/NOK is Norges Bank `EXR/B.EUR.NOK.SP`. | Norges Bank's official daily rate. |
| B4 | Canonical series are a JSON block inside `facts/ledger.md`, parsed by code. | "Each fact appears once": agents and code read the same file. |
| B5 | Values are `Decimal`. SSB values are re-quantised to the table's published decimals. | SSB's JSON sends 3.0 as `3`. The rounding rule needs the published precision. |
| B6 | Recordings are keyed by a hash of the exact URL, stored in `tests/recorded/http/`. The allowlist is checked in replay mode too. | Deterministic offline tests; replay cannot be used to sneak in another host. |
| B7 | Weekend 1 adds a `norfigures latest` command. | It is the "done when" check for weekend 1, and stays as a handy smoke test. |

## Pending (spec section 7 edge-case defaults)

The other rows in spec section 7 await Haakon's decision: unemployment, revisions, forecasts, rounding, hedged figures, percent vs
points, monthly vs 12-month, no figure, missing period, policy rate on a date.
These must be settled before the verifier (weekend 2) encodes them.

## Other open items

- Source a link for the 2 % inflation target in the ledger.
- Terms of use for both APIs (both appear open with no key; SSB rate limit
  observed at 40 requests per minute).
- MCP dependency: stdlib-only or one dependency. Weekend 3.
- LLM model and cost per run. Weekend 3.
