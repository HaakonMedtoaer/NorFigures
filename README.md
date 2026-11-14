# NorFigures

*Kort på norsk: NorFigures sjekker tall om inflasjon, styringsrente og eurokurs i en tekst mot SSB og Norges Bank, og sier fra når tallet ikke stemmer.*

NorFigures checks the numbers in a text against official Norwegian sources.
It finds claims about inflation (KPI, KPI-JAE), the policy rate and EUR/NOK,
fetches the official figure from SSB or Norges Bank, and reports which claims
match, which don't, and which could not be checked.

**The AI interprets, the source verifies.** A model may read a sentence and
pick the right series. It never supplies a number.

> Status: early build (weekend 1 of 4). The source layer works; claim checking
> arrives next. See [`docs/spec.md`](docs/spec.md) and [`docs/decisions.md`](docs/decisions.md).

## Try it

Python 3.10+, standard library only.

```bash
git clone https://github.com/HaakonMedtoaer/norfigures && cd norfigures
PYTHONPATH=src python -m norfigures latest --offline   # recorded responses, no network
PYTHONPATH=src python -m norfigures latest             # live from SSB and Norges Bank
```

## Tests

```bash
python -m unittest
```

Tests run offline against recorded API responses in `tests/recorded/`.
Refresh them with `NORFIGURES_RECORD=1 PYTHONPATH=src python -m norfigures latest`.

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
