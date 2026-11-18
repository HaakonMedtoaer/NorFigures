# Facts ledger

The single place for fixed facts, indicator definitions and canonical series.
Each fact appears once. Agents read this file. If a fact they need is missing,
they report it as missing. They never fill the gap from model memory.

Code reads the `series` JSON block below. Edit it here and nowhere else.

## Fixed facts

| Fact | Value | Source | Confirmed |
|---|---|---|---|
| Norges Bank's operational inflation target | 2 % annual CPI growth over time | Regulation on monetary policy (Forskrift om pengepolitikken), 2018 | 2026-11-14 (needs a source link before weekend 3) |
| CPI reference year in SSB tables from 2026 | 2025 = 100 | SSB table 14706 notes | 2026-11-14 |
| SSB release timing for KPI | KPI for month M is published around the 10th of month M+1 | Observed pattern; confirm against SSB's release calendar | 2026-11-15 (to verify) |

## Indicator definitions

- **KPI (CPI)**: consumer price index, headline. "Inflasjon", "prisvekst" and
  "inflation" with no qualifier mean the **12-month change in KPI**.
- **KPI-JAE (CPI-ATE)**: CPI adjusted for tax changes and excluding energy
  products. Norges Bank's main core measure. Called "kjerneinflasjon" or
  "underliggende inflasjon" in ordinary text.
- **Monthly change**: change from the previous month, in percent. Signalled by
  phrases such as "fra september til oktober" or "siste måned".
- **Policy rate (styringsrenten)**: the sight deposit rate. A value applies to a
  date, and the rate in force on a date is the last observation on or before it.
- **EUR/NOK**: Norges Bank's daily exchange rate, NOK per 1 EUR, business days only.

## Canonical series

Confirmed against the live APIs on 2026-11-14.

- SSB table 14706 replaced the closed table 05327 (and 03013 for headline CPI)
  at the 2026 rebase. The `KPI` row of 14706 is the canonical headline CPI, so
  every CPI series reads from one table **for periods from 2026-01**.
- For periods up to 2025-12, the rates **as SSB published them** are in the
  closed tables 03013 (KPI) and 05327 (KPI-JAE). Rates recalculated in 14706
  can differ by 0.1 (14706's own note says so): February 2025 KPI was published
  as 3.6 % but is 3.5 % in 14706. Each SSB series therefore has a `history`
  entry: for periods up to `until`, read that table instead (B24). Confirmed
  2026-11-18 against the March 2025 release (KPI 3.6, KPI-JAE 3.4).
- SSB rate limit observed: 40 requests per 60 seconds.
- Norges Bank series are business-daily (`B`). There are no weekend values.

```json series
{
  "kpi_12m": {
    "indicator": "kpi", "measure": "12_month_change", "unit": "percent",
    "concept": "Headline CPI, 12-month change",
    "source": "ssb", "frequency": "M", "table": "14706",
    "selection": {"KPIavledetSerie": "KPI", "ContentsCode": "Tolvmanedersendring"},
    "history": [{"until": "2025-12", "table": "03013",
                 "selection": {"Konsumgrp": "TOTAL", "ContentsCode": "Tolvmanedersendring"}}],
    "confirmed": "2026-11-14"
  },
  "kpi_monthly": {
    "indicator": "kpi", "measure": "monthly_change", "unit": "percent",
    "concept": "Headline CPI, change from previous month",
    "source": "ssb", "frequency": "M", "table": "14706",
    "selection": {"KPIavledetSerie": "KPI", "ContentsCode": "Manedsendring"},
    "history": [{"until": "2025-12", "table": "03013",
                 "selection": {"Konsumgrp": "TOTAL", "ContentsCode": "Manedsendring"}}],
    "confirmed": "2026-11-14"
  },
  "kpi_jae_12m": {
    "indicator": "kpi_jae", "measure": "12_month_change", "unit": "percent",
    "concept": "CPI-ATE (core), 12-month change",
    "source": "ssb", "frequency": "M", "table": "14706",
    "selection": {"KPIavledetSerie": "KPI-JAE", "ContentsCode": "Tolvmanedersendring"},
    "history": [{"until": "2025-12", "table": "05327",
                 "selection": {"Konsumgrp": "JAE_TOTAL", "ContentsCode": "Tolvmanedersendring"}}],
    "confirmed": "2026-11-14"
  },
  "policy_rate": {
    "indicator": "policy_rate", "measure": "level", "unit": "percent",
    "concept": "Norges Bank policy rate (sight deposit rate)",
    "source": "norges_bank", "frequency": "B", "flow": "IR", "key": "B.KPRA.SD.R",
    "confirmed": "2026-11-14"
  },
  "eurnok": {
    "indicator": "eurnok", "measure": "level", "unit": "nok_per_eur",
    "concept": "EUR/NOK exchange rate, NOK per 1 EUR",
    "source": "norges_bank", "frequency": "B", "flow": "EXR", "key": "B.EUR.NOK.SP",
    "confirmed": "2026-11-14"
  }
}
```
