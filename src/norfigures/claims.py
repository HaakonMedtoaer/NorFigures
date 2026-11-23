"""Claim schema: what the extractor and mapper hand to the verifier.

Validation is strict and loud. Input that fails is a failed extraction
(exit 3) and is never repaired silently (spec section 10).

A claim dict as produced by extractor + mapper:

    {
      "id": "c1",
      "source_text": "Inflasjonen var 3,1 % i oktober",
      "status": "checkable",              # STATUSES
      "indicator": "kpi",                 # INDICATORS, or any name if out_of_scope
      "measure": "12_month_change",       # MEASURES
      "period": "2026-10",                # YYYY-MM, YYYY-MM-DD, YYYY, or null
      "unit": "percent",                  # UNITS
      "stated_value": 3.1,                # number or string; decimals are kept
      "hedged": false,                    # "rundt", "omtrent", "about" (D10)
      "labels": [],
      "mappings": [{"series_id": "kpi_12m"}, {"series_id": "kpi_jae_12m"}]
    }

`mappings` holds one entry, or two or more when the claim has several valid
readings (D4). The first entry is the canonical reading.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

STATUSES = ("checkable", "forecast", "no_figure", "ambiguous", "out_of_scope")
INDICATORS = ("kpi", "kpi_jae", "policy_rate", "eurnok", "unemployment")
MEASURES = ("12_month_change", "monthly_change", "level", "change")
UNITS = ("percent", "percentage_points", "nok_per_eur")

PERIOD_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")


class SchemaError(Exception):
    """Claims failed validation. Carries every problem found, not just the first."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("invalid claims:\n  - " + "\n  - ".join(problems))


@dataclass(frozen=True)
class Claim:
    id: str
    source_text: str
    status: str
    indicator: str | None = None
    measure: str | None = None
    period: str | None = None
    unit: str | None = None
    stated_value: Decimal | None = None
    hedged: bool = False
    labels: tuple[str, ...] = ()
    mappings: tuple[str, ...] = ()   # ledger series IDs, canonical first
    notes: str = ""                  # e.g. phrase-table overrides, mapper notes


def parse_json(text: str) -> object:
    """Parse JSON keeping decimals exact: 4.0 stays Decimal('4.0')."""
    return json.loads(text, parse_float=Decimal)


def to_decimal(raw) -> Decimal:
    """Accept 3.1, '3.1' or '3,1'. Reject bools, NaN and infinities."""
    if isinstance(raw, bool):
        raise ValueError("boolean is not a number")
    if isinstance(raw, float):
        raw = repr(raw)
    if isinstance(raw, str):
        raw = raw.strip().replace("−", "-").replace(",", ".")
    try:
        d = Decimal(raw)
    except (InvalidOperation, TypeError) as e:
        raise ValueError(f"not a number: {raw!r}") from e
    if not d.is_finite():
        raise ValueError(f"not a finite number: {raw!r}")
    return d


def validate(data: object, known_series: dict) -> list[Claim]:
    """Validate a list of claim dicts. Raises SchemaError listing all problems."""
    problems: list[str] = []
    if isinstance(data, dict) and "claims" in data:
        data = data["claims"]
    if not isinstance(data, list):
        raise SchemaError(["top level must be a list of claims (or {\"claims\": [...]})"])

    claims, seen = [], set()
    for i, raw in enumerate(data):
        where = f"claim[{i}]"
        if not isinstance(raw, dict):
            problems.append(f"{where}: must be an object")
            continue
        p0 = len(problems)

        def need(cond, msg):
            if not cond:
                problems.append(f"{where} ({raw.get('id', '?')}): {msg}")

        unknown = set(raw) - {"id", "source_text", "status", "indicator", "measure", "period",
                              "unit", "stated_value", "hedged", "labels", "mappings", "notes"}
        need(not unknown, f"unknown fields {sorted(unknown)}")

        cid = raw.get("id")
        need(isinstance(cid, str) and _ID_RE.match(cid or ""), "id must be a short string")
        need(cid not in seen, f"duplicate id {cid!r}")
        seen.add(cid)
        need(isinstance(raw.get("source_text"), str) and raw["source_text"].strip(),
             "source_text must be a non-empty string")
        status = raw.get("status")
        need(status in STATUSES, f"status must be one of {STATUSES}")

        indicator = raw.get("indicator")
        measure = raw.get("measure")
        unit = raw.get("unit")
        period = raw.get("period")
        need(indicator is None or isinstance(indicator, str), "indicator must be a string or null")
        need(measure is None or measure in MEASURES, f"measure must be one of {MEASURES} or null")
        need(unit is None or unit in UNITS, f"unit must be one of {UNITS} or null")
        need(period is None or (isinstance(period, str) and PERIOD_RE.match(period)),
             "period must be YYYY, YYYY-MM, YYYY-MM-DD or null")

        stated = None
        if raw.get("stated_value") is not None:
            try:
                stated = to_decimal(raw["stated_value"])
            except ValueError as e:
                need(False, f"stated_value: {e}")

        hedged = raw.get("hedged", False)
        need(isinstance(hedged, bool), "hedged must be true or false")
        notes = raw.get("notes", "")
        need(isinstance(notes, str), "notes must be a string")
        labels = raw.get("labels", [])
        need(isinstance(labels, list) and all(isinstance(x, str) for x in labels),
             "labels must be a list of strings")

        mappings = raw.get("mappings", [])
        ids: list[str] = []
        if not isinstance(mappings, list):
            need(False, "mappings must be a list")
        else:
            for m in mappings:
                sid = m.get("series_id") if isinstance(m, dict) else None
                if sid not in known_series:
                    need(False, f"mapping series_id {sid!r} is not in the ledger")
                    continue
                if isinstance(m, dict) and m.get("source") not in (None, known_series[sid].source):
                    need(False, f"mapping source {m.get('source')!r} does not match ledger for {sid}")
                ids.append(sid)
            need(len(ids) == len(set(ids)), "mappings must not repeat a series")

        if status == "checkable":
            need(indicator in INDICATORS, f"checkable claims need indicator in {INDICATORS}")
            need(measure is not None, "checkable claims need a measure")
            need(stated is not None, "checkable claims need a stated_value")
            need(len(ids) >= 1, "checkable claims need at least one mapping")
        if status == "out_of_scope":
            need(isinstance(indicator, str) and indicator,
                 "out_of_scope claims must name the indicator")

        if len(problems) == p0:
            claims.append(Claim(
                id=cid, source_text=raw["source_text"], status=status,
                indicator=indicator, measure=measure, period=period, unit=unit,
                stated_value=stated, hedged=hedged, labels=tuple(labels),
                mappings=tuple(ids), notes=notes if isinstance(notes, str) else ""))

    if problems:
        raise SchemaError(problems)
    return claims
