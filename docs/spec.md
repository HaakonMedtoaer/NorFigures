> Copy of the project spec, exported 2026-11-14 from the spec doc (rev 12).
> The doc is the working copy; refresh this file when the spec changes.

# NorFigures: project spec

Status: draft v0.2. Build starts the week of 16 Nov 2026. Name: NorFigures.

## 1. Summary and problem

NorFigures is a command-line fact verifier for Norwegian economic figures. It reads ordinary text, finds claims about inflation, the policy rate and the EUR/NOK exchange rate, fetches the official value from SSB or Norges Bank, and reports whether each claim matches.

The problem is simple. People and AI models both put confident, wrong numbers in documents. A report says inflation was 3.1 % when the published figure was different, or quotes core inflation as if it were the headline number. Law firms, consultancies and public bodies sign their names under such documents, and checking every figure by hand is slow enough that it often gets skipped.

One rule shapes the whole design: the AI interprets, the source verifies. A model may decide what a sentence is claiming and which series answers it. It never supplies a number.

## 2. Goals and non-goals

**Goals**

- Verify numeric claims for three indicators against official open data.
- Show the exact series and query behind every verdict, so a reader can catch a bad mapping.
- Name every claim that could not be checked. Nothing is dropped quietly.
- Run in CI with meaningful exit codes.
- Clone and run with the Python standard library, plus one LLM API key for the agent steps.
- Serve as a readable work sample of directing AI agents with written contracts and guardrails.

**Non-goals**

- General fact checking of non-numeric statements.
- Judging forecasts, opinions or causal claims.
- A web UI for checking, a database or a hosted service. The flow map in section 14 is a read-only viewer.
- Coverage of all Norwegian statistics.
- Legal-grade assurance. The tool is a second reader and does not replace one.

## 3. Users and audience

| Reader | What they need |
| --- | --- |
| Analyst, editor or associate checking a draft | A table of claims with verdicts and sources, in under a minute |
| Developer or agent calling it in a pipeline | JSON output, stable exit codes, read-only MCP tools |
| Recruiter or hiring manager reading the README | To understand in 30 seconds what it does, see it catch an error, and see which decisions Haakon made |
| Technical interviewer | Agent contracts, tests and guardrails they can open and judge |

## 4. How it works

Five steps, of which two use an LLM.

1. **Extract** (agent). Text goes in, structured claims come out.
2. **Map** (agent). Each claim gets a source, a series and a query, chosen from the facts ledger and the MCP search tools.
3. **Fetch** (code). The query runs against the official API.
4. **Compare** (code). Stated value against official value, under the tolerance rules.
5. **Report** (code). Table, JSON and exit code.

### Worked example

All numbers below are illustrative and are not real published values.

Input, with publication date 15 Nov 2026:

> Inflasjonen var 3,1 % i oktober. Norges Bank holdt styringsrenten på 4,0 %, og analytikerne venter at kronen svekkes til 12,00 mot euro neste år.

Output:

| # | Claim | Stated | Official | Verdict | Source and query |
| --- | --- | --- | --- | --- | --- |
| 1 | Inflasjonen var 3,1 % i oktober | 3.1 % | 2.8 % | MISMATCHED | SSB, KPI 12-month change, 2026-10, table `<id>` |
| 2 | styringsrenten på 4,0 % | 4.0 % | 4.0 % | MATCHED | Norges Bank, policy rate, 2026-11-15, series `<id>` |
| 3 | kronen svekkes til 12,00 mot euro neste år | 12.00 | n/a | CANNOT VERIFY (forecast, not checkable) | none |

Notes printed under the table: claim 1 is flagged `ambiguous_measure` because "inflasjonen" could mean KPI or KPI-JAE. Both were checked and neither matched. Exit code: 1.

## 5. Components

### CLI

```
norfigures check <file|-> [--published YYYY-MM-DD] [--format table|json] [--offline]
```

Reads a file or stdin. `--published` gives the reference date for period inference. `--offline` replays recorded API responses.

### Agents

Three narrow agents live in `agents/`, each with a written contract in its own markdown file, and a shared `CLAUDE.md` at the repo root.

| Agent | Input | Output | Must not |
| --- | --- | --- | --- |
| Extractor | Raw text, publication date | List of claims: source\_text, indicator, measure, period, unit, stated\_value, status | Rewrite or correct numbers; skip a numeric claim without reporting it; guess a missing period |
| Mapper | One claim, facts ledger, MCP search and describe tools | mapping {source, series\_id, query}, or unmapped with a reason | Fetch or state values; choose a series the ledger does not list as canonical without flagging it; pick silently between two valid measures |
| Explainer (optional) | Finished claim record | One or two plain sentences per verdict | Change a verdict; introduce any number absent from the record |

Verification is plain code. No agent compares numbers.

### MCP server

A small server wrapping both sources, read-only by construction: it implements HTTP GET requests to two allowlisted hosts and nothing else.

| Tool | Purpose |
| --- | --- |
| `search_series(source, text)` | Find candidate tables or series by keyword |
| `describe_series(source, series_id)` | Return dimensions, units, frequency, latest period |
| `fetch_values(source, series_id, query)` | Return observations for a query |

### Verifier

A deterministic module. It takes a mapped claim, calls the same fetch code the MCP server uses, applies the tolerance and unit rules in section 7, and sets `official_value`, `retrieved_at` and `verdict`.

### Facts ledger

A single file, `facts/ledger.md`. It holds fixed facts (for example the 2 % inflation target), indicator definitions, and which series is canonical for which concept. Each fact appears once. Agents read the ledger; if a fact is missing they report it as missing and do not fill the gap from model memory.

### Report format

A table on stdout for people, and `--format json` producing the full list of claim records plus a summary block with counts per verdict.

### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | All claims matched |
| 1 | At least one mismatch |
| 2 | No mismatch, but at least one claim could not be verified |
| 3 | Bad input, bad config, or source unreachable |

A mismatch outranks an unverifiable claim. Text with no checkable claims exits 2 with a message, since "nothing checked" should never look like a pass.

## 6. Claim data model

```json
{
  "id": "c1",
  "source_text": "Inflasjonen var 3,1 % i oktober",
  "indicator": "kpi | policy_rate | eurnok",
  "measure": "12_month_change | monthly_change | level",
  "period": "2026-10",
  "period_inferred": true,
  "unit": "percent | percentage_points | nok_per_eur",
  "stated_value": 3.1,
  "status": "checkable | forecast | no_figure | ambiguous | out_of_scope",
  "mapping": {
    "source": "ssb | norges_bank",
    "series_id": "<confirmed during build>",
    "query": {}
  },
  "official_value": 2.8,
  "retrieved_at": "2026-11-15T09:12:00Z",
  "verdict": "matched | mismatched | cannot_verify",
  "labels": ["ambiguous_measure"],
  "notes": "Checked KPI and KPI-JAE; neither matches."
}
```

`status` is set by the extractor and describes the claim. `verdict` is set by code and describes the outcome. `labels` carry the reason for any `cannot_verify`.

## 7. Edge-case rules

All rows are decided; see docs/decisions.md (D4 to D16).

| Case | Proposed default |
| --- | --- |
| Ambiguous measure (KPI vs KPI-JAE) | **Decided (D4):** when a claim has two valid readings and the text gives too little context to choose, show both official figures side by side and explain in plain words what each one measures. Label ambiguous\_measure. Verdict: matched if either reading matches, mismatched if neither (D5). |
| Unemployment (AKU vs NAV registered) | Outside the three MVP indicators. Report as out\_of\_scope and name it. The ambiguity rule above applies once the indicator is added. |
| Revisions and vintage | Compare against the latest published value and record retrieved\_at. First-published vintage is a later feature. |
| Forecasts | Future tense, forecast verbs ("venter", "anslår", "expects") or a future period give status forecast and verdict cannot\_verify with label forecast\_not\_checkable. |
| Rounding | A stated value matches when the official value, rounded to the same number of decimals as stated, is equal. EUR/NOK: same rule for a named date; for a period without a named date, matched if the value falls within the period's daily low and high. |
| Hedged figures | "About", "rundt", "nærmere" widen the tolerance to plus or minus one unit in the last stated digit, and the label approximate is added. |
| Percent vs percentage points | Changes in a rate are in percentage points. "Renten økte med 0,25 prosent" is checked as 0.25 points and labelled unit\_assumed. |
| Monthly vs 12-month change | "Inflasjonen" with no qualifier means 12-month change. "Fra september til oktober" means monthly change. A claim that fits neither pattern is ambiguous. |
| No number ("record low") | Status no\_figure, verdict cannot\_verify, reported by name. Out of MVP scope. |
| Missing period | With --published, infer the latest period released on or before that date and set period\_inferred. Without it, cannot\_verify with label period\_missing. |
| Policy rate on a date | Use the rate in force on the stated date, or on the publication date if none is given. |

## 8. Data sources

| Source | Used for | Access |
| --- | --- | --- |
| SSB Statbank API (PxWebApi) | KPI and KPI-JAE | Table-based API. A query selects values per dimension and returns JSON. Table metadata can be requested. |
| Norges Bank data API (SDMX) | Policy rate, EUR/NOK | Series are addressed by dataflow and key, with a period filter. JSON and CSV formats are offered. |

Both are understood to be open with no API key required. **To verify during build:** key requirement, terms of use, rate limits, and the current API version at SSB.

No table IDs, series keys or endpoint paths are fixed in this spec. Task for weekend 1: confirm the exact IDs for the five series (KPI 12-month, KPI monthly, KPI-JAE, policy rate, EUR/NOK), and write them into the ledger with the date confirmed.

## 9. Testing

One command runs everything: `python -m unittest`. Tests run offline against recorded API responses stored in `tests/recorded/`. A separate, opt-in command refreshes the recordings from the live APIs.

The suite holds 15 to 20 fixed cases:

| Category | Cases | Example |
| --- | --- | --- |
| Correct claims | 3 | Right KPI figure, right period |
| Deliberately wrong numbers | 3 | Policy rate off by 0.25 points |
| Ambiguous claims | 3 | "Inflasjonen" where only KPI-JAE fits |
| Forecasts | 2 | "Ventes å falle til 2 % neste år" |
| Mapping traps | 4 | Monthly change stated as annual; right number, wrong month |
| No figure | 2 | "Rekordsvak krone" |
| Bad input | 2 | Empty file; binary file |

Agent outputs for the fixture texts are also recorded, so the deterministic half of the pipeline is tested without an LLM call. A smaller live set checks the agents themselves and is run by hand before releases.

## 10. Guardrails

- **Host allowlist.** All network code goes through one function that refuses any host other than the two official API hosts. A test asserts this.
- **Read-only by construction.** The fetch layer has no method other than GET.
- **Number provenance check.** Code rejects any official\_value that did not come from a fetch response in the same run.
- **Pre-commit and pre-push hook.** Runs the tests and scans for API keys and for hosts outside the allowlist.
- **Schema validation.** Agent output that fails the claim schema is reported as a failed extraction (exit 3) and is never repaired silently.
- **Loud accounting.** The report ends with a count line: claims found, matched, mismatched, unverifiable. The numbers must add up, and a test checks that they do.

## 11. Repo layout

```
norfigures/
├── README.md
├── CLAUDE.md
├── LICENSE
├── agents/
│   ├── extractor.md
│   ├── mapper.md
│   └── explainer.md
├── facts/
│   └── ledger.md
├── src/norfigures/
│   ├── cli.py
│   ├── pipeline.py
│   ├── verifier.py
│   ├── report.py
│   ├── net.py              # allowlist, GET only
│   ├── sources/
│   │   ├── ssb.py
│   │   └── norges_bank.py
│   └── mcp_server.py
├── tests/
│   ├── cases/              # fixture texts and expected verdicts
│   ├── recorded/           # API and agent recordings
│   └── test_*.py
├── hooks/
│   └── pre-commit
└── docs/
    ├── spec.md
    └── decisions.md
```

## 12. README plan

Written before any feature beyond the MVP.

1. **First screen.** One-line problem statement, a short animation of a run with one indicator per worker (see section 14, not a terminal recording), and a sample table that shows a caught mismatch.
2. **Quick start.** Clone, set one environment variable, run the example.
3. **Architecture diagram.** Five boxes: extract, map, fetch, compare, report. The two agent boxes are visually distinct from the three code boxes.
4. **"What Claude wrote and what I decided."** Claude Code wrote the code. The section lists Haakon's decisions with links to `docs/decisions.md`: the never-supplies-a-number rule, the edge-case defaults, the exit codes, what was cut.
5. **Known limits.** Three indicators, latest vintage only, numeric claims only.
6. **Tests badge** and the one test command.

## 13. Milestones

Counted in working weekends, since hours are not fixed.

| Weekend | Deliverable | Done when |
| --- | --- | --- |
| 1 | Source layer: confirmed series IDs in the ledger, net.py with allowlist, fetch for all three indicators, first recordings | A script prints the latest value for each indicator, offline and live |
| 2 | Claim schema, verifier, report, exit codes, fixture cases with hand-written claims, run event log | All deterministic tests pass with no LLM involved |
| 3 | Extractor and mapper agents with contracts, MCP server, end-to-end CLI | The full loop passes all 15 to 20 cases |
| 4 | README, diagram, decisions log, hooks, CI badge, publish | A stranger can clone and run the example in five minutes |

Stop rule: when the loop passes all cases, write the README. No new indicators before that.

## 14. Live flow map (after MVP)

A live flow map shows a run moving through the pipeline, so anyone can see which part does what. It is planned as weekend 5, after the MVP is published.

**What it shows**

- The pipeline as boxes: input text, extractor, mapper, fetch, compare and report, with the MCP server, facts ledger and the two APIs beside them. Agent boxes and code boxes have different colours, as in the README diagram.
- Each claim as a marker moving from box to box. The active box lights up while it works.
- Verdict colours at the end: matched, mismatched, cannot verify.
- Guardrail hits in red where they happen: a blocked host, a schema failure, a number with no fetch behind it.
- Click a box to see what went in and what came out for the selected claim, including the exact query.

**How it stays small**

- The pipeline writes one event per step to a JSON-lines log (run\_id, claim\_id, stage, status, detail, timestamp). The log is built in the MVP (weekend 2), since it also helps debugging and testing.
- The flow map only reads that log: one static HTML file, no framework, no build step. It never controls the pipeline.
- Two modes. Live: `norfigures check --flow` opens the page and follows the log as the run happens. Replay: plays back a recorded run.
- Replay needs no API key, so a recorded run can be hosted free on GitHub Pages. A recruiter can watch a run in the browser without installing anything, and the README animation is made from it.

**Not in the flow map**

- Editing claims or rerunning steps from the page.
- History across runs, dashboards or metrics.

Open item: live mode via a stdlib server with server-sent events, or by polling the log file. Decide in weekend 5.

### README animation (decided 18 Nov 2026)

The README's first screen shows an animation of a run instead of a terminal recording: one indicator per worker, showing who is running and which source it is checking. It is staged, not live, but every label in it comes from a real recorded run.

| Indicator | Kind | What its caption shows while it runs |
| --- | --- | --- |
| Extractor | AI agent (Claude Haiku 5.5) | "Reading the text…", then "Found 3 claims" |
| Phrase tables + mapper | Code | The phrase matched and the series chosen, e.g. "inflasjonen → KPI and KPI-JAE" |
| SSB | Source | Table, series and period being checked, e.g. "Table 14706 · KPI 12-month · 2026-10" |
| Norges Bank | Source | Series and date being checked, e.g. "IR/B.KPRA.SD.R · 2026-11-12" |
| Verifier | Code | Stated against official value per claim, e.g. "3.1 vs 3.6" |
| Report | Code | The verdicts and the exit code |

- States: idle (grey), running (pulsing), done (green). The AI indicator has its own colour, as in the README diagram.
- Claims run one after another, so the viewer sees each claim handed from indicator to indicator. It ends on the verdicts: matched, mismatched, cannot verify.
- Content comes from the run log of the spec's worked example, replayed from recorded responses. Only the timing is staged, so each step stays visible.
- A script makes it from the log: an animated SVG or GIF in `docs/`, about 10 to 15 seconds, looping. No screen recording and no API key.
- Built in weekend 5 together with the flow map, which reads the same log and shares its look.

## 15. Out of scope and later ideas

- More indicators: unemployment (AKU) first, right after the MVP (D16); then GDP, wage growth, house prices.
- NAV as a second source for registered unemployment.
- First-published vintage checking, for claims made before a revision.
- A full web UI or browser extension.
- PDF and Word document input.
- A legacy-format converter as a second input path into the same verify loop.
- Checking non-numeric claims such as "record low" or "highest since 2008" by computing over the series (kept open, D13).

## 16. Open questions

| Question | Suggestion |
| --- | --- |
| Name | Decided: NorFigures. Check that the GitHub repo name and PyPI package name are free. |
| License | MIT. |
| README language | English, with a short Norwegian summary at the top, since examples are Norwegian. |
| LLM and cost | Which model and API the agents use, and the cost per run. Measure on the fixture set in weekend 3 and state it in the README. |
| Bring-your-own key | Assumed yes. The offline mode lets a reader run the tests without any key. |
| Hosting | None needed for a CLI. |
| MCP dependency | Stdlib-only implementation of the protocol, or one allowed dependency for the server alone. Decide in weekend 3. |
| Edge-case defaults | All rows decided (D4 to D16). See docs/decisions.md. |

## 18. What we discovered during the build

The MVP works as planned: the full loop passes all 20 test cases on real Claude Haiku 5.5 output, at about $0.0006 per check. Sections 1 to 17 are the original plan, left as written. Building it turned up the findings below, and each one changed the plan for the reason given. The Ref column points to `docs/decisions.md`.

| Date | Area | What we found | What we changed | Ref |
| --- | --- | --- | --- | --- |
| 14 Nov | Data | SSB closed tables 05327 and 03013 when it rebased CPI to 2025 = 100 | All CPI series read from table 14706, which holds both KPI and KPI-JAE | B1 |
| 14 Nov | Data | SSB's JSON sends 3.0 as the number 3, losing a decimal the rounding rule needs | Values are restored to the decimals the table says it publishes | B5 |
| 14 Nov | Data | SSB allows 40 requests a minute; neither API needs a key | Noted in the ledger; no key handling needed | Ledger |
| 14 Nov | Data | Norges Bank series have business days only, and send values like "4" with no decimals | The rate on a date is the last observation on or before it; rounding handles "4" vs "4,0" | B2, D15 |
| 14 Nov | Process | The cloud session could not reach the data APIs | A cloud environment that allows only the two official hosts | — |
| 15 Nov | Design | An ambiguous claim needs two or more readings, but the spec's claim had room for one mapping | A claim carries a list of mappings, canonical first | B8, D4 |
| 15 Nov | Design | "Styringsrenten var 4,5 % i oktober" has no single official value | A month on a daily series is checked against that month's low and high | B10 |
| 15 Nov | Design | There is no release calendar in the data; SSB publishes KPI around the 10th | On days 1 to 15, both possible months are checked | B11 |
| 15 Nov | Design | The extractor could call a future period checkable | Code treats any period after the publication date as a forecast | B13 |
| 15 Nov | Design | Most of what people write about these figures is a predictable phrase | Phrase tables, applied by code after the model; where they disagree, the tables win and the report says so | D19 |
| 15 Nov | Design | With phrase tables, choosing the series became a lookup | The mapper agent was dropped; mapping is plain code | B18 |
| 15 Nov | AI | Extraction is a narrow, well-defined task | Claude Haiku 5.5 instead of a larger model | D17 |
| 15 Nov | AI | The AI step needs outside packages; nothing else does | Two layers: a standard-library core, and an optional install for the AI step and MCP server | D18 |
| 15 Nov | AI | "Never rewrite a number" can be checked, not just asked for | Code rejects any claim that is not word for word in the text, or whose number is not in it | B20 |
| 15 Nov | Process | The cloud session cannot call the Anthropic API with a personal key | Model outputs are recorded once on a personal computer; tests replay them | B21 |
| 15 Nov | Design | Real wording puts words between verb and "med": "økte renten med 0,25" | The change-verb rule allows words in between | B22 |
| 18 Nov | AI | First recorded run: 17 of 20 cases passed. Haiku called core inflation a "level" once and left one measure empty | The mapping rules now set the measure for KPI claims, with a note in the report | B23 |
| 18 Nov | Process | The text pipeline crashed right after extraction; no test had run that step without a model | Fixed, and covered by a test that needs no recordings | — |
| 18 Nov | Process | Reading text from a file adds a newline, which changed the recording key | Text is trimmed before extraction | — |
| 18 Nov | Process | The pre-commit hook blocked the model's host in the source code | That host is allowed in exactly one module, the one that calls the model | B19 |
| 18 Nov | Design | A terminal recording would not show which part does what | The README gets an animation with one indicator per worker | Section 14 |
| 18 Nov | Data | Real headlines from March 2025: SSB's rebased table 14706 recalculates older rates. February 2025 KPI was published as 3.6 % but is 3.5 % in 14706, so correct headlines were flagged as wrong | Periods up to December 2025 read the closed tables that hold the rates as published (03013 for KPI, 05327 for KPI-JAE) | B24, D6 |
| 18 Nov | Design | "Matvareprisene steg 8,6 prosent" would have been compared with overall KPI and flagged as wrong | Sub-indices (food, electricity, rent, fuel) are out of scope, unless the claim also names overall inflation | B25 |
| 19 Nov | Design | SSB's own articles: "Tolvmånedersveksten steg 1,3 prosentpoeng" was compared with the rate itself and flagged as wrong, though 3.6 − 2.3 = 1.3 | A change in an inflation rate in percentage points is checked as this month's rate minus last month's; its sign comes from words like "nedgang" and "høyere" | B27, B31 |
| 19 Nov | Design | With a careless extractor, four of nine claims in one SSB article were false alarms: electricity, food, chocolate and restaurant prices checked against overall KPI | General patterns for parts of KPI ("prisene på X", "sjokoladeprisene") and other rates ("boliglånsrenten"), plus more 12-month phrasings | B26, B28 |
| 19 Nov | Data | Norges Bank: "Styringsrenten settes ned til 4,25 prosent" was flagged on its publication day, because the cut takes effect the next business day | A rate decision with no date is checked against the rate the day after publication | B29 |
| 19 Nov | Design | Real sentences take their subject from the previous one ("En oppgang på 0,6 prosentpoeng fra januar"), and a loose change-verb rule read "hevet mye for å få bukt med" as a change | A claim that names no index checks both KPI and KPI-JAE; change verbs need "med" right before the amount; the extractor contract got real-text rules | B30, B31 |
