# Phrase tables

Reference tables of what people write about the figures NorFigures checks.
They are used twice:

1. The extractor agent gets them as reference, so it knows the vocabulary.
2. Code applies them after extraction (`src/norfigures/lexicon.py`), and maps
   claims to series without a model (`src/norfigures/mapper.py`). When the
   tables and the model disagree, the tables win, and the report says so
   with the label `lexicon_override`.

Matching is case-insensitive, on whole words. Each phrase appears once.
Code reads the `json phrases` block below. Edit it here and nowhere else.

## How the rules work

| Table | Effect when found in a claim's `source_text` |
|---|---|
| `hedges` | `hedged: true` (D10 tolerance, label `approximate`) |
| `forecast_markers` | a `checkable` claim becomes `forecast` (D7) |
| `measures.12_month_change` / `monthly_change` / `monthly_change_regex` | sets the measure (D12) |
| `measures.12_month_change_regex` | "fra februar 2024 til februar 2025": the same month a year apart is a 12-month change (B26) |
| `points_words` | "prosentpoeng", "prosentenheter": for KPI, a **change in the rate**, checked as this month's rate minus last month's (B27) |
| `rate_decision_markers` | "settes ned", "holdes uendret": a rate decision, which takes effect the day after it is announced (B29) |
| `out_of_scope_regex.sub_index` | "prisene på elektrisitet", "prisveksten for matvarer", "sjokoladeprisene": a sub-index, even when a general word is present (B28) |
| `out_of_scope_regex.other_rate` | "boliglånsrenten", "innskuddsrenten": another interest rate, not the policy rate (B28) |
| `direction_down` / `direction_up` | the sign of a change: "en nedgang på 0,3 prosentpoeng" is -0.3. Both or neither found: the size is compared and the report says the direction was not read (B31) |
| `change_verbs` | followed later by "med" or "by" directly before the amount ("økte renten med 0,25"; not "hevet mye for å få bukt med den høye prisveksten"): for the policy rate or EUR/NOK, measure `change` (D11) |
| `indicators.kpi_jae` | indicator `kpi_jae` |
| `indicators.inflation_generic` | KPI vs KPI-JAE is ambiguous: both are checked, KPI first (D4); 12-month change unless a measure phrase says otherwise (D12) |
| `indicators.kpi_growth_nouns` | headline KPI, 12-month change unless a measure phrase says otherwise (D12) |
| `indicators.prices_generic` | headline KPI; monthly vs 12-month is ambiguous unless a measure phrase is found (D12) |
| `out_of_scope` | claim is `out_of_scope`, named by its key (D16) |
| `out_of_scope.sub_index` | food, electricity, rent, fuel: part of KPI, not KPI itself, so out of scope; **only when** the claim names no overall-inflation word ("prisveksten falt, trukket ned av strømprisene" is still KPI) (B25) |
| `indicators.unemployment` | unemployment rate (D16). With no source word, checked against AKU (trend, then the seasonally adjusted 3-month average) and NAV's registered rate; matched if any fits (D4, B41, D20) |
| `indicators.unemployment_aku` | names the AKU source: AKU only (B43) |
| `indicators.unemployment_nav` | names NAV's registered unemployment: NAV only (D20). A claim the extractor put out of scope for this reason is brought back in scope when it has a percent |
| `indicators.unemployment_trend` / `unemployment_3mma` | picks that one AKU series instead of both (B41) |
| `out_of_scope.jobseekers` | partly unemployed and all job seekers ("delvis ledige", "arbeidssøkere"): a different NAV figure, out of scope (D20) |
| `out_of_scope_regex.unemployment_group` | unemployment for a group ("ledigheten blant unge", "ungdomsledigheten"), not the total (B43) |
| `record_words` | with no number: `no_figure` (D13) |

```json phrases
{
  "hedges": [
    "rundt", "omtrent", "cirka", "ca.", "nærmere", "om lag", "i overkant av",
    "i underkant av", "drøyt", "knapt", "snaut", "anslagsvis",
    "about", "around", "roughly", "approximately", "nearly", "almost"
  ],
  "forecast_markers": [
    "venter", "ventes", "forventer", "forventes", "anslår", "anslås", "spår", "spås",
    "regner med", "kommer til å", "vil", "neste år", "til neste år", "prognose", "prognosen",
    "expects", "expected to", "forecasts", "is forecast", "projected", "will"
  ],
  "measures": {
    "12_month_change": [
      "siste tolv måneder", "siste 12 måneder", "tolvmånedersveksten", "tolvmånedersvekst",
      "12-månedersveksten", "12-månedersvekst", "fra samme måned i fjor", "fra samme tid i fjor",
      "de siste tolv månedene", "siste tolv månedene", "de siste 12 månedene", "siste år", "det siste året",
      "årsveksten", "årsvekst", "year on year", "year-on-year", "12-month", "twelve-month"
    ],
    "monthly_change": [
      "siste måned", "fra forrige måned", "fra måneden før", "månedsveksten", "månedsvekst",
      "month on month", "month-on-month", "from the previous month"
    ],
    "12_month_change_regex": [
      "fra (januar|februar|mars|april|mai|juni|juli|august|september|oktober|november|desember) (\\d{4}) til \\1 (\\d{4})",
      "(sammenlignet med|enn i|enn) (januar|februar|mars|april|mai|juni|juli|august|september|oktober|november|desember)( \\d{4})? (i fjor|for ett år siden)",
      "i (januar|februar|mars|april|mai|juni|juli|august|september|oktober|november|desember) (\\d{4}) enn i \\1 (\\d{4})",
      "for ett år siden", "sammenlignet med samme måned i fjor"
    ],
    "monthly_change_regex": [
      "fra (januar|februar|mars|april|mai|juni|juli|august|september|oktober|november|desember) (\\d{4}) til (?!\\1)(januar|februar|mars|april|mai|juni|juli|august|september|oktober|november|desember) (\\d{4})",
      "fra (januar|februar|mars|april|mai|juni|juli|august|september|oktober|november|desember) til (januar|februar|mars|april|mai|juni|juli|august|september|oktober|november|desember)",
      "from (january|february|march|april|may|june|july|august|september|october|november|december) to (january|february|march|april|may|june|july|august|september|october|november|december)"
    ]
  },
  "points_words": [
    "prosentpoeng", "prosentpoengs", "prosentenhet", "prosentenheter", "%-poeng",
    "percentage point", "percentage points"
  ],
  "rate_decision_markers": [
    "settes ned", "settes opp", "satt ned", "satt opp", "holdes uendret", "holdt uendret",
    "sette styringsrenten ned", "sette styringsrenten opp", "heve styringsrenten",
    "besluttet", "rentebeslutning", "rentemøtet", "is reduced", "is raised", "unchanged at"
  ],
  "direction_down": [
    "nedgang", "nedgangen", "falt", "sank", "ned", "lavere", "reduksjon", "redusert", "kuttet",
    "senket", "avtok", "svakere", "fell", "lower", "decrease", "decreased", "cut", "reduced"
  ],
  "direction_up": [
    "oppgang", "oppgangen", "økning", "økningen", "økte", "steg", "opp", "høyere", "hevet",
    "sterkere", "rose", "higher", "increase", "increased", "raised"
  ],
  "change_verbs": [
    "økte", "økt", "steg", "sank", "falt", "kuttet", "kuttes", "satt opp", "satt ned",
    "hevet", "senket", "redusert", "raised", "cut", "increased", "lowered", "reduced"
  ],
  "indicators": {
    "kpi_explicit": ["kpi", "konsumprisindeksen", "konsumprisindeks", "cpi", "consumer price index"],
    "kpi_growth_nouns": ["kpi-veksten", "kpi-vekst", "cpi growth"],
    "kpi_jae": [
      "kpi-jae", "kjerneinflasjon", "kjerneinflasjonen", "underliggende inflasjon",
      "underliggende prisvekst", "cpi-ate", "core inflation"
    ],
    "inflation_generic": [
      "inflasjon", "inflasjonen", "prisvekst", "prisveksten", "prisstigning", "prisstigningen",
      "inflation"
    ],
    "prices_generic": ["prisene", "prices", "konsumprisene"],
    "policy_rate": [
      "styringsrente", "styringsrenten", "renten", "rentenivået", "policy rate", "key rate",
      "sight deposit rate", "foliorenten"
    ],
    "eurnok": [
      "euro", "euroen", "eurokurs", "eurokursen", "eur/nok", "eurnok", "kronekurs", "kronekursen",
      "kronen", "krone"
    ],
    "unemployment": [
      "arbeidsledighet", "arbeidsledigheten", "ledighet", "ledigheten", "ledighetsraten",
      "ledighetsprosenten", "ledighetsnivået", "arbeidsledige", "unemployment", "unemployment rate"
    ],
    "unemployment_aku": [
      "aku", "aku-ledighet", "aku-ledigheten", "aku-tallene", "arbeidskraftundersøkelsen",
      "arbeidskraftundersøkelse", "labour force survey"
    ],
    "unemployment_nav": [
      "registrert ledighet", "registrerte ledigheten", "registrert arbeidsledighet",
      "registrerte arbeidsledigheten", "registrert arbeidsledige", "registrerte arbeidsledige",
      "registrert helt ledige", "helt ledige", "nav", "nav-tall", "nav-tallene",
      "registered unemployment"
    ],
    "unemployment_trend": ["trend", "trenden", "trendtall", "trendtallet", "trendtallene"],
    "unemployment_3mma": [
      "sesongjustert", "sesongjusterte", "glidende gjennomsnitt", "tremåneders", "tre måneders",
      "tremånedersperioden", "seasonally adjusted", "three-month average", "3-month average"
    ]
  },
  "out_of_scope": {
    "jobseekers": [
      "delvis ledige", "helt og delvis ledige", "arbeidssøkere", "arbeidssøkerne",
      "arbeidssøkere på tiltak", "job seekers"
    ],
    "gdp": ["bnp", "bruttonasjonalprodukt", "bruttonasjonalproduktet", "gdp"],
    "wage_growth": ["lønnsvekst", "lønnsveksten", "wage growth"],
    "house_prices": ["boligpris", "boligpriser", "boligprisene", "boligprisveksten", "house prices"],
    "sub_index": [
      "matpris", "matpriser", "matprisene", "matvarepris", "matvarepriser", "matvareprisene",
      "strømpris", "strømpriser", "strømprisene", "strømprisen", "husleie", "husleien", "husleiene",
      "drivstoffprisene", "bensinprisen", "dieselprisen", "energiprisene", "flyprisene",
      "food prices", "electricity prices", "rents", "fuel prices"
    ]
  },
  "out_of_scope_regex": {
    "sub_index": [
      "\\bpris(ene|en|vekst|veksten|stigning|stigningen)? (på|for) (?!varer og tjenester|[-−]?\\d|januar|februar|mars|april|mai|juni|juli|august|september|oktober|november|desember|året|fjoråret|perioden|samme)",
      "\\b(?!konsum)\\w{3,}pris(ene|en|er)\\b",
      "\\b\\w*veksten (på|for) (?!kpi|konsum|varer og tjenester|[-−]?\\d|januar|februar|mars|april|mai|juni|juli|august|september|oktober|november|desember|året|fjoråret|perioden|samme)",
      "\\bkpi[a-zæøå]{2,}\\b"
    ],
    "other_rate": [
      "\\b(?!styrings|folio)\\w{3,}renten?\\b"
    ],
    "unemployment_group": [
      "\\b(arbeids)?ledighet(en)? (blant|for) ",
      "\\b(ungdoms|langtids|innvandrer)\\w*ledighet(en)?\\b"
    ]
  },
  "record_words": [
    "rekord", "rekordhøy", "rekordlav", "rekordsvak", "rekordsterk", "historisk lav",
    "historisk høy", "record high", "record low", "all-time high", "all-time low"
  ]
}
```

## Known gaps

- "som ventet" (as expected) is past tense and deliberately not a forecast marker.
- "renten" can mean a bank's mortgage rate. The extractor decides from context;
  the tables only confirm a policy-rate reading.
- Context outside the claim's own words (for example "Kjerneinflasjonen ...
  Den var 3 %") is the extractor's job; the tables only see `source_text`.
