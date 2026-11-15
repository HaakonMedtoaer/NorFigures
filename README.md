# NorFigures

*Kort på norsk: NorFigures sjekker tall om inflasjon, styringsrente og eurokurs i en tekst mot SSB og Norges Bank, og sier fra når tallet ikke stemmer.*

NorFigures checks the numbers in a text against official Norwegian sources.
It finds claims about inflation (KPI, KPI-JAE), the policy rate and EUR/NOK,
fetches the official figure from SSB or Norges Bank, and reports which claims
match, which don't, and which could not be checked.

**The AI interprets, the source verifies.** A model may read a sentence and
pick the right series. It never supplies a number.

> Status: early build (weekend 3 of 4). The full loop is built: an AI extractor
> (Claude Haiku 5.5) reads the text, phrase tables and plain code map each claim
> to a series, and the verifier checks it. Recorded model outputs for the test
> texts are next. See [`docs/spec.md`](docs/spec.md) and [`docs/decisions.md`](docs/decisions.md).

## Try it

Python 3.10+, standard library only.

```bash
git clone https://github.com/HaakonMedtoaer/norfigures && cd norfigures
PYTHONPATH=src python -m norfigures latest --offline   # recorded responses, no network
PYTHONPATH=src python -m norfigures latest             # live from SSB and Norges Bank

# Check hand-written claims (the spec's worked example):
python -c "import json;print(json.dumps(json.load(open('tests/cases/20_spec_worked_example.json'))['claims']))" > example.json
PYTHONPATH=src python -m norfigures check --claims example.json --published 2026-11-15
```

Check a text (needs the agents extra and an Anthropic API key):

```bash
pip install -e '.[agents]'
export ANTHROPIC_API_KEY=...        # your own key
echo "Inflasjonen var 3,1 % i oktober." | norfigures check - --published 2026-11-15
```

Exit codes: 0 all matched, 1 at least one mismatch, 2 something could not be
verified (or nothing was checked), 3 bad input, bad config or source unreachable.

## Tests

```bash
python -m unittest
```

Tests run offline against recorded API responses in `tests/recorded/`, and
include 20 fixture cases in `tests/cases/` (correct, wrong, ambiguous,
forecasts, mapping traps, no figure, edge cases). Refresh recordings with:

```bash
NORFIGURES_RECORD=1 python -m unittest
```

## MCP server

Three read-only tools (`search_series`, `describe_series`, `fetch_values`) over
the same fetch code, for use from any MCP client:

```bash
python -m norfigures.mcp_server
```

## Sources

| Indicator | Source | Series |
|---|---|---|
| KPI, 12-month and monthly change | SSB | table 14706 |
| KPI-JAE, 12-month change | SSB | table 14706 |
| Policy rate | Norges Bank | IR/B.KPRA.SD.R |
| EUR/NOK | Norges Bank | EXR/B.EUR.NOK.SP |

Canonical definitions live in [`facts/ledger.md`](facts/ledger.md).

## Licence

MIT
