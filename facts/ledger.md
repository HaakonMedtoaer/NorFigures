# Facts ledger

The single place for fixed facts, indicator definitions and canonical series.
Each fact appears once. Agents read this file. If a fact they need is missing,
they report it as missing. They never fill the gap from model memory.

Code reads the `series` JSON block below. Edit it here and nowhere else.

## Fixed facts

| Fact | Value | Source | Confirmed |
|---|---|---|---|
| Norges Bank's operational inflation target | "en årsvekst i konsumprisene som over tid er nær 2 pst." (annual CPI growth close to 2 % over time) | Bestemmelse om pengepolitikken, adopted 18 September 2026; same wording as the 2018 and 2019 regulations it replaces. [Norges Bank press release](https://www.norges-bank.no/aktuelt/nyheter/Pressemeldinger/2026/2026-09-18-mandat/) | 2026-11-19 |
| CPI reference year in SSB tables from 2026 | 2025 = 100 | SSB table 14706 notes | 2026-11-14 |
| SSB release timing for KPI | KPI for month M is published on the 10th of month M+1, or the nearest working day (Fri 9 Oct 2026, Mon 11 May 2026); July is later (15 Jul 2026). Inference checks both possible months on days 1 to 15 (B11), which covers all of these. | [SSB article list](https://www.ssb.no/priser-og-prisindekser/konsumpriser/statistikk/konsumprisindeksen/artikler), 2025 and 2026 | 2026-11-19 |
| SSB release timing for AKU (labour force survey) | Monthly figures for month M are published 3 to 4 weeks after M ends ("Månedlig publisering av trendtall og sesongjusterte tall 3-4 uker etter utløpet av måneden"). Observed for February to September 2026: day 21 to 26 of month M+1 (September 2026: 22 October). Inference uses the window day 20 to 27 (B42). | [SSB AKU statistics page](https://www.ssb.no/arbeid-og-lonn/sysselsetting/statistikk/arbeidskraftundersokelsen), [AKU articles](https://www.ssb.no/arbeid-og-lonn/sysselsetting/statistikk/arbeidskraftundersokelsen/artikler) | 2026-11-23 |
| SSB's headline AKU unemployment rate | The **trend** figure. The statistics page's key-figure table is headed "Trendtall" (September 2026: 4,6 % of the labour force, 141 000 people), and table 13760's note recommends the trend and the 3-month moving average of seasonally adjusted figures; the other two series are "hovedsakelig av hensyn til ekspertbrukere". | SSB AKU statistics page; table 13760 notes | 2026-11-23 |
| NAV release timing for registered unemployment | NAV publishes month M late in month M itself, always on a Friday at 08.00 ("Hovedtall om arbeidsmarkedet publiseres alltid på fredager"): November 2026 on 27 November, December 2026 on 18 December. The table file on the statistics page can follow a few days later (the October 2026 file is dated 5 November). Inference uses days 18 to 31 of month M (D20). | [NAV publiseringskalender](https://www.nav.no/no/nav-og-samfunn/statistikk/publiseringskalender) | 2026-11-23 |
| Break in NAV's registered unemployment | A new job-seeker register broke the series for April to July 2025 ("brudd i statistikken for april til juli 2025"). NAV recommends comparing from July 2025 onwards and does not publish year-on-year comparisons across it. Levels are kept as published; a change across the break is not computed. | [NAV: Helt ledige](https://www.nav.no/no/nav-og-samfunn/statistikk/arbeidssokere-og-stillinger-statistikk/helt-ledige); note in table HL050 | 2026-11-23 |
| Terms of use for NAV's statistics | CC BY 4.0 (data.norge.no lists both NAV "helt ledige" datasets under it). No API: the figures are published as files on www.nav.no. | [data.norge.no: Statistikk helt arbeidsledige](https://data.norge.no/en/datasets/2a822275-534e-3bd3-8712-68f20c53f719) | 2026-11-23 |
| Terms of use for the data | SSB: CC BY 4.0, including the API (credit SSB). Norges Bank: open API, no sign-in; site terms allow copying with Norges Bank named as source. No rate limit is published; SSB's API answers 40 requests a minute. | [SSB licence](https://www.ssb.no/diverse/lisens), [SSB API](https://www.ssb.no/api), [Norges Bank copyright](https://www.norges-bank.no/Opphavsrett/), [Norges Bank open data](https://www.norges-bank.no/tema/statistikk/apne-data/) | 2026-11-19 |

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
- **Unemployment (AKU)**: SSB's labour force survey, unemployed persons aged 15 to 74
  as a percent of the labour force. "Arbeidsledigheten" and "ledigheten" with no
  source named mean this figure (D16), but may be NAV's registered unemployment,
  which is not covered yet (B43). The 3-month moving average is named after its
  **middle** month: the figure for February is the average of January to March.
- **Registered unemployment (NAV)**: people registered as wholly unemployed with
  NAV ("registrert ledighet", "helt ledige") as a percent of the labour force. A
  different, lower figure than AKU (October 2026: 2,0 against AKU's 4,6 for
  September). Partly unemployed and job seekers on programmes ("delvis ledige",
  "arbeidssøkere") are not included and stay out of scope (D20).

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
- AKU: table 13760 (confirmed 2026-11-23; 2006M01 to 2026M09, updated 22 October
  2026). `ArbledProsArbstyrk`, both sexes (`Kjonn` 0), ages 15 to 74, published
  with one decimal. `Justering` T is the trend (canonical, SSB's headline); 3MGG
  is the 3-month moving average of seasonally adjusted figures, named after its
  middle month, so its latest month comes one release later. S (seasonally
  adjusted) and IS (unadjusted) are not used. Trend figures are revised each
  month (August 2026: published 4,5, now 4,6); under D6 the latest value counts.
- `release_window` (monthly series): month M is published between these days of
  month M+1 (month M itself with `"release_month_offset": 0`). Without it, the
  KPI default applies: days 1 to 15 of month M+1 (B11).
- NAV (confirmed 2026-11-23): no API. Table HL050 ("Helt ledige. Kjønn og alder.
  Tidsserie måned"), sheet "2. Kjønn Prosent av arbeidsstyrken", row "I alt",
  one decimal (cell format `#,##0.0`). The file for the current year is linked
  from the "Helt ledige" page as `<YYYYMM>_HL050 ... .xlsx` under a URL with a
  content hash, so it is found on the page at each run (`sources/nav.py`). Earlier
  years: the December file on `arkiv-helt-ledige.<year>` (2020 onwards). The
  labour force is SSB's AKU up to 2021, SSB's register data from 2022.

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
  "aku_trend": {
    "indicator": "unemployment", "measure": "level", "unit": "percent",
    "concept": "Unemployment rate (AKU), trend, % of labour force",
    "source": "ssb", "frequency": "M", "table": "13760",
    "selection": {"Kjonn": "0", "Alder": "15-74", "Justering": "T", "ContentsCode": "ArbledProsArbstyrk"},
    "release_window": [20, 27],
    "confirmed": "2026-11-23"
  },
  "aku_3mma": {
    "indicator": "unemployment", "measure": "level", "unit": "percent",
    "concept": "Unemployment rate (AKU), seasonally adjusted 3-month moving average (middle month), % of labour force",
    "source": "ssb", "frequency": "M", "table": "13760",
    "selection": {"Kjonn": "0", "Alder": "15-74", "Justering": "3MGG", "ContentsCode": "ArbledProsArbstyrk"},
    "release_window": [20, 27],
    "confirmed": "2026-11-23"
  },
  "nav_registered": {
    "indicator": "unemployment", "measure": "level", "unit": "percent",
    "concept": "Registered unemployment (NAV), wholly unemployed, % of labour force",
    "source": "nav", "frequency": "M", "table": "HL050",
    "selection": {"sheet": ["Kjønn", "Prosent"], "row": "I alt"},
    "release_window": [18, 31], "release_month_offset": 0,
    "breaks": [["2025-04", "2025-07"]],
    "confirmed": "2026-11-23"
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
