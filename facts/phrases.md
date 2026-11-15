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
| `change_verbs` | followed later by "med" or "by" ("økte renten med 0,25"): for the policy rate or EUR/NOK, measure `change` (D11) |
| `indicators.kpi_jae` | indicator `kpi_jae` |
| `indicators.inflation_generic` | KPI vs KPI-JAE is ambiguous: both are checked, KPI first (D4); 12-month change unless a measure phrase says otherwise (D12) |
| `indicators.kpi_growth_nouns` | headline KPI, 12-month change unless a measure phrase says otherwise (D12) |
| `indicators.prices_generic` | headline KPI; monthly vs 12-month is ambiguous unless a measure phrase is found (D12) |
| `out_of_scope` | claim is `out_of_scope`, named by its key (D16) |
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
      "årsveksten", "årsvekst", "year on year", "year-on-year", "12-month", "twelve-month"
    ],
    "monthly_change": [
      "siste måned", "fra forrige måned", "fra måneden før", "månedsveksten", "månedsvekst",
      "month on month", "month-on-month", "from the previous month"
    ],
    "monthly_change_regex": [
      "fra (januar|februar|mars|april|mai|juni|juli|august|september|oktober|november|desember) til (januar|februar|mars|april|mai|juni|juli|august|september|oktober|november|desember)",
      "from (january|february|march|april|may|june|july|august|september|october|november|december) to (january|february|march|april|may|june|july|august|september|october|november|december)"
    ]
  },
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
    ]
  },
  "out_of_scope": {
    "unemployment": ["arbeidsledighet", "arbeidsledigheten", "ledighet", "ledigheten", "ledighetsraten", "unemployment"],
    "gdp": ["bnp", "bruttonasjonalprodukt", "bruttonasjonalproduktet", "gdp"],
    "wage_growth": ["lønnsvekst", "lønnsveksten", "wage growth"],
    "house_prices": ["boligpris", "boligpriser", "boligprisene", "boligprisveksten", "house prices"]
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
