"""Deterministic mapper: claim -> ledger series, canonical first.

Replaces the mapper agent (decision B18). Uses only the ledger and the phrase
tables, so it can never invent a series or a number. A claim it cannot map
gets no mappings and is reported by name as `cannot_verify`.
"""

from __future__ import annotations

from .ledger import Series
from .lexicon import hints


def _find(series: dict[str, Series], indicator: str, measure: str) -> str | None:
    for sid, s in series.items():
        if s.indicator == indicator and s.measure == measure:
            return sid
    return None


def map_claim(raw: dict, series: dict[str, Series]) -> tuple[list[str], str | None]:
    """Return (series IDs, note). An empty list means unmapped; the note says why."""
    if raw.get("status") != "checkable":
        return [], None
    ind, measure = raw.get("indicator"), raw.get("measure")
    h = hints(raw.get("source_text", ""), number=raw.get("stated_value"))
    period = raw.get("period") or ""
    year = len(period) == 4   # "inflasjonen i 2025": an annual figure (D21)

    if ind in ("policy_rate", "eurnok"):
        sid = _find(series, ind, "level")
        if measure not in ("level", "change", None):
            return [], f"{ind} is a level series; '{measure}' cannot be checked on it."
        return ([sid], None) if sid else ([], f"No ledger series for {ind}.")

    if ind == "unemployment":
        # AKU (D16): trend is SSB's headline; the 3-month average is the other series
        # SSB recommends (B41). NAV's registered rate (D20). A source word picks one;
        # with none, all are checked and any can match (D4).
        if measure not in ("level", "change", None):
            return [], f"unemployment is a rate; '{measure}' cannot be checked on it."
        aku = {"trend": ["aku_trend"], "3mma": ["aku_3mma"]}.get(h.unemployment_series,
                                                                ["aku_trend", "aku_3mma"])
        nav = ["nav_registered"]
        if year:
            # A year: SSB's annual AKU rate (as published, and break adjusted) and
            # NAV's annual average (D21).
            aku, nav = ["aku_annual", "aku_annual_break_adjusted"], ["nav_registered_annual"]
        if h.unemployment_nav and not (h.unemployment_aku or h.unemployment_series):
            want = nav
        elif h.unemployment_aku or h.unemployment_series:
            want = aku
        else:
            want = aku + nav
        ids = [sid for sid in want if sid in series]
        missing = [sid for sid in want if sid not in series]
        return ids, ("Not in the ledger yet: " + ", ".join(missing) + ".") if missing else None

    if ind not in ("kpi", "kpi_jae"):
        return [], f"Indicator '{ind}' has no series in the ledger."

    # Which measure(s)? A measure phrase decides (D12). Without one, the nouns
    # "inflasjon"/"prisvekst"/"kjerneinflasjon"/"KPI-veksten" mean 12-month change; anything
    # else ("prisene steg", "KPI steg") could be either.
    if measure == "change":
        # A change in the rate, in points (B27): the 12-month rate unless a phrase says monthly.
        measures = [h.measure or "12_month_change"]
    elif h.measure:
        measures = [h.measure]
    elif ind == "kpi_jae" or h.inflation_generic or h.kpi_growth_noun:
        measures = ["12_month_change"]
    else:
        measures = ["12_month_change", "monthly_change"]

    # Which index? Generic inflation words without "KPI" could mean headline or
    # core; headline is canonical (D4, ledger).
    named = h.kpi_explicit or h.kpi_jae or h.inflation_generic or h.prices_generic
    if ind == "kpi_jae":
        indicators = ["kpi_jae"]
    elif h.inflation_generic and not h.kpi_explicit:
        indicators = ["kpi", "kpi_jae"]
    elif not named:
        # The claim's own words name no index ("En oppgang på 0,6 prosentpoeng fra
        # januar"): either could be meant, so both are checked (D4, B30).
        indicators = ["kpi", "kpi_jae"]
    else:
        indicators = ["kpi"]

    if year:
        # A year has two readings (D21, D4): the annual average change, SSB's own
        # annual figure, and the 12-month change in December. A change in the rate
        # ("0,3 prosentpoeng lavere enn i 2024") is between two annual rates only.
        measures = ["annual_change"] if measure == "change" else ["annual_change", "12_month_change"]

    out, missing = [], []
    for i in indicators:
        for m in measures:
            sid = _find(series, i, m)
            if sid:
                out.append(sid)
            else:
                missing.append(f"{i} {m.replace('_', ' ')}")
    note = None
    if missing:
        note = "Not in the ledger yet: " + ", ".join(missing) + "."
    return out, note
