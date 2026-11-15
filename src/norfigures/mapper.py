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
    h = hints(raw.get("source_text", ""))

    if ind in ("policy_rate", "eurnok"):
        sid = _find(series, ind, "level")
        if measure not in ("level", "change", None):
            return [], f"{ind} is a level series; '{measure}' cannot be checked on it."
        return ([sid], None) if sid else ([], f"No ledger series for {ind}.")

    if ind not in ("kpi", "kpi_jae"):
        return [], f"Indicator '{ind}' has no series in the ledger."

    # Which measure(s)? A measure phrase decides (D12). Without one, the nouns
    # "inflasjon"/"prisvekst"/"kjerneinflasjon"/"KPI-veksten" mean 12-month change; anything
    # else ("prisene steg", "KPI steg") could be either.
    if h.measure:
        measures = [h.measure]
    elif ind == "kpi_jae" or h.inflation_generic or h.kpi_growth_noun:
        measures = ["12_month_change"]
    else:
        measures = ["12_month_change", "monthly_change"]

    # Which index? Generic inflation words without "KPI" could mean headline or
    # core; headline is canonical (D4, ledger).
    if ind == "kpi_jae":
        indicators = ["kpi_jae"]
    elif h.inflation_generic and not h.kpi_explicit:
        indicators = ["kpi", "kpi_jae"]
    else:
        indicators = ["kpi"]

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
