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
| D6 | 2026-11-14 | Revisions: compare against the latest published value; record `retrieved_at`. | First-published vintage is a later feature. | Haakon |
| D7 | 2026-11-14 | Forecasts (future tense, "venter", "anslår", "expects", future period): status `forecast`, verdict `cannot_verify`, label `forecast_not_checkable`. | A forecast cannot be checked against published data. | Haakon |
| D8 | 2026-11-14 | Rounding: round the official value half-up to the stated number of decimals; matched if equal. "3,6 %" matches 3.56, not 3.54. | Matches how people quote figures. | Haakon |
| D9 | 2026-11-14 | EUR/NOK for a period without a named date: matched if the stated value lies within the period's daily low and high. | No single official value exists for a period. | Haakon |
| D10 | 2026-11-14 | Hedged figures ("rundt", "omtrent", "nærmere", "about"): tolerance of plus or minus one unit in the last stated digit; label `approximate`. | The writer signalled imprecision. | Haakon |
| D11 | 2026-11-14 | Changes in a rate are percentage points. "Renten økte med 0,25 prosent" is checked as 0.25 points; label `unit_assumed`. | Common usage; the label keeps it visible. | Haakon |
| D12 | 2026-11-14 | "Inflasjonen" with no qualifier means 12-month change; "fra september til oktober" means monthly change; anything else is ambiguous and follows D4/D5. | One rule for all ambiguity. | Haakon |
| D13 | 2026-11-14 | No figure ("rekordsvak krone"): status `no_figure`, verdict `cannot_verify`, reported by name. Kept open for later: checking record claims (e.g. "highest since …") by computing over the series. | Out of MVP scope, but a likely extension. | Haakon |
| D14 | 2026-11-14 | Missing period: with `--published`, infer the latest period published on or before that date and set `period_inferred`; without it, `cannot_verify` with label `period_missing`. | Never guess silently. | Haakon |
| D15 | 2026-11-14 | Policy rate on a date: the rate in force on the stated date, or on the publication date if none is given; non-business days use the last business day before. | The series has business-day observations only. | Haakon |
| D16 | 2026-11-14 | Unemployment: `out_of_scope` in the MVP, reported by name. First indicator added after the MVP is SSB's AKU (labour force survey). NAV registered unemployment comes later as a second source; D4/D5 then cover AKU vs NAV ambiguity. | Keeps the MVP at three indicators (stop rule). AKU uses the existing SSB host; NAV needs a new adapter and host. | Haakon |
| D17 | 2026-11-15 | The extractor agent uses Claude Haiku 5.5 (`claude-haiku-5-5`), effort `medium`, measured on the fixture cases. Switch only an agent that misses cases to Sonnet 5.5. | Narrow, well-specified task; about a tenth of a cent per run. | Haakon |
| D18 | 2026-11-15 | Two layers. Core (verifier, reports, tests, `check --claims`) stays standard-library only. The `agents` extra (`pip install 'norfigures[agents]'`) adds `anthropic` and `mcp` for the extractor and the MCP server. | Clone-and-run and offline tests keep working with no installs and no key. | Haakon |
| D19 | 2026-11-15 | Phrase tables (`facts/phrases.md`) for what people write: hedges, forecast verbs, measure phrases, indicator words. Code applies them after the model; where they disagree, the tables win and the claim is labelled `lexicon_override`. | No need for the model to do what a lookup does; fewer model mistakes, and every override is visible. | Haakon |

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

## Weekend 2 build choices (for review)

| # | Choice | Why |
|---|---|---|
| B8 | A claim carries `mappings` (a list, canonical reading first) instead of the spec's single `mapping`. | D4 needs two or more readings per claim. |
| B9 | Only the first mapping must match the claim's measure; alternative readings only need a compatible unit. | Alternatives exist because the measure is uncertain (D12: monthly vs 12-month). |
| B10 | A month on a daily series (policy rate, EUR/NOK) is checked against the month's low and high. | D9 for EUR/NOK; the same reading is the fairest one for "styringsrenten var 4,5 % i oktober". |
| B11 | Inferred KPI period (D14): from day 16 of a month, last month; on days 1 to 15, both last month and the month before, since SSB publishes around the 10th. Label `period_ambiguous`; D5 applies. | We have no release calendar yet. A release-calendar lookup could replace this later. |
| B12 | A change in a rate ("økte med 0,25") = last value in the period minus last value before it. | Works for a date or a month. |
| B13 | Guard: a period after the publication date (or today) is treated as a forecast, even if the extractor said `checkable`. | Code, not the model, decides what can be published yet. |
| B14 | Annual periods ("inflasjonen i 2025") are `cannot_verify` with label `annual_not_supported`. | Annual averages are a different series; later feature. |
| B15 | JSON output writes numbers as strings ("4.0"). | Keeps the published precision exact. |
| B16 | `check --claims FILE` takes hand-written claims until the agents exist (weekend 3). Run logs go to `runs/<run_id>.jsonl` (git-ignored). | Weekend 2 is deterministic only. |
| B17 | Provenance check: every official value must equal the observations fetched in this run, tracked by object identity, or the run fails with exit 3. | Spec section 10, "number provenance check". |

## Weekend 3 build choices (for review)

| # | Choice | Why |
|---|---|---|
| B18 | The mapper is plain code (`mapper.py`), not an agent. It maps with the ledger and the phrase tables, following D4 and D12. The spec's mapper agent and `agents/mapper.md` are dropped. | With D19 the mapping is a lookup. A model would add cost and a way to be wrong, and nothing it could know that the tables don't. |
| B19 | The model is called only through `agents/llm.py`, pinned to `https://api.anthropic.com` (override: `NORFIGURES_ANTHROPIC_BASE_URL`). The data allowlist in `net.py` stays two hosts. The model gets no tools. | Model traffic and data traffic never mix; the model cannot fetch or change a number. |
| B20 | Extractor output is checked in code: each `source_text` must be a verbatim span of the input, and each `stated_value` must be a number in that span. Failure is a failed extraction (exit 3). | Enforces "never rewrite a number" instead of asking for it. |
| B21 | Model outputs are recorded per (model, prompt, publication date, text) in `tests/recorded/agents/`. A changed prompt or phrase table means re-recording; until then the end-to-end test skips with a message rather than passing. | Tests stay offline and free; stale recordings never pass silently. |
| B23 | After mapping, the mapper's canonical series sets the claim's measure for KPI and KPI-JAE (D12); for a rate or exchange rate an empty measure becomes `level`. A changed measure is noted and labelled `measure_from_rules`. | First recorded run: Haiku gave core inflation as `level` and left "Prisene steg" without a measure. D12 is a code rule, so code applies it. |
| B24 | SSB series read periods up to 2025-12 from the closed tables that hold the rates as published (03013 for KPI, 05327 for KPI-JAE), and later periods from 14706. Set per series in the ledger's `history`. | Found with real headlines from March 2025: KPI for February 2025 was published as 3.6 % but is 3.5 % in 14706 after the rebase; KPI-JAE 3.4 vs 3.5. Without this, correct headlines are flagged as wrong. Fits D6 ("latest published value"). |
| B25 | Sub-indices (food, electricity, rent, fuel) are out of scope, unless the same claim names overall inflation ("prisveksten falt, trukket ned av strømprisene" is still KPI). | "Matvareprisene steg 8,6 prosent" would otherwise be compared with headline KPI and flagged as wrong. |
| B26 | "fra februar 2024 til februar 2025", "høyere enn oktober for ett år siden", "sammenlignet med oktober i fjor" mean 12-month change (phrase tables). | Found in SSB release articles. |
| B27 | A change in an inflation rate in percentage points ("Tolvmånedersveksten steg 1,3 prosentpoeng") is checked as this month's rate minus last month's. | SSB writes this in every release. Before, it was compared with the rate itself: a false alarm on correct text. |
| B28 | General patterns for parts of KPI and for other rates: "prisene på X", "veksten for X", compounds like "sjokoladeprisene" or "KPImat", and compounds like "boliglånsrenten". "Prisene på X" marks a sub-index even when a general word is present. | With a careless extractor, four of nine claims in one SSB article were false alarms. |
| B29 | A policy-rate decision ("settes ned", "holdes uendret") with no date is checked against the rate the day after publication. | Norges Bank's decisions take effect the next business day; "Styringsrenten settes ned til 4,25 prosent" was flagged on its own publication day. |
| B30 | A KPI claim whose own words name no index is checked against both KPI and KPI-JAE (D4). | "En oppgang på 0,6 prosentpoeng fra januar" gets its subject from the previous sentence. |
| B31 | The sign of a change comes from direction words ("nedgang", "falt", "høyere"); with no or mixed direction words, only the size is compared and the report says so. Change verbs need "med"/"by" directly before the amount. | "En nedgang på 0,3 prosentpoeng" is -0.3; "hevet mye for å få bukt med den høye prisveksten" is not a change of 0.25. |
| B22 | Phrase-table rule for change verbs: the verb, then "med"/"by" later in the claim ("økte renten med 0,25"). KPI growth nouns ("KPI-veksten") mean 12-month change by default. | Real wording puts words between the verb and "med"; "KPI-veksten" is read like "inflasjonen". |

## Pending

All spec section 7 edge cases are decided (D4 to D16).

## Other open items

- Source a link for the 2 % inflation target in the ledger.
- Terms of use for both APIs (both appear open with no key; SSB rate limit
  observed at 40 requests per minute).
- Done 2026-11-18: weekend 3 "done when" met. The full loop passes all 20
  cases on recorded Claude Haiku 5.5 output. Measured: about 4,400 input and
  230 output tokens per text; $0.011 for all 20 texts, about $0.0006 per check
  (Haiku 5.5 list prices, 2026-11-15). Haiku was enough; no Sonnet needed (D17).
- 2026-11-19: four real long texts added (SSB articles for February 2025 and
  October 2026; Norges Bank press releases for June 2025 and November 2026).
  41 claims: 22 matched, 19 correctly not checkable, 0 false alarms, with both a
  careful and a careless extractor. Haiku recordings for them, and a re-record of
  everything after the phrase-table and contract changes, are pending.
- 2026-11-18, after B24/B25: re-recorded 28 texts (20 cases + 8 real headlines
  from the February and March 2025 releases). All pass end to end, no false
  alarms on the headlines. 131,864 input and 6,062 output tokens, $0.0162 in
  total, $0.00058 per text.
