"""Deterministic phrase rules from facts/phrases.md.

`review()` corrects what the extractor said, using only the claim's own words.
It can tighten a claim (hedged, forecast, a stated measure) but never invents a
number or a period. Every change is labelled `lexicon_override` and noted.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .net import REPO_ROOT

PHRASES_PATH = REPO_ROOT / "facts" / "phrases.md"
_BLOCK = re.compile(r"```json phrases\n(.*?)\n```", re.S)


class PhrasesError(Exception):
    """facts/phrases.md is missing or malformed. Exit code 3."""


@lru_cache(maxsize=4)
def load(path: Path | None = None) -> dict:
    path = Path(path or PHRASES_PATH)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise PhrasesError(f"cannot read {path}: {e}") from e
    blocks = _BLOCK.findall(text)
    if len(blocks) != 1:
        raise PhrasesError(f"{path.name} must contain exactly one ```json phrases block")
    try:
        data = json.loads(blocks[0])
    except json.JSONDecodeError as e:
        raise PhrasesError(f"phrases block is not valid JSON: {e}") from e
    for key in ("hedges", "forecast_markers", "measures", "change_verbs", "indicators",
                "out_of_scope", "record_words"):
        if key not in data:
            raise PhrasesError(f"phrases block is missing '{key}'")
    return data


def _pattern(phrase: str) -> re.Pattern:
    # Whole-word match that also works for phrases ending in "." or containing "/" and "-".
    return re.compile(r"(?<![\w-])" + re.escape(phrase.lower()) + r"(?![\w-])")


def found(text: str, phrases: list[str]) -> list[str]:
    low = text.lower()
    return [p for p in phrases if _pattern(p).search(low)]


@dataclass
class Hints:
    """What the phrase tables see in one piece of text."""

    hedges: list[str] = field(default_factory=list)
    forecast: list[str] = field(default_factory=list)
    measure: str | None = None            # "12_month_change" | "monthly_change" | None
    measure_phrase: str | None = None
    change_verb: str | None = None
    kpi_explicit: bool = False
    kpi_growth_noun: bool = False
    kpi_jae: bool = False
    inflation_generic: bool = False
    prices_generic: bool = False
    out_of_scope: str | None = None       # key, e.g. "unemployment"
    out_of_scope_specific: bool = False   # found by a pattern like "prisene på X" (B28)
    points: str | None = None             # "prosentpoeng" etc. (B27)
    rate_decision: str | None = None      # "settes ned" etc. (B29)
    direction: int = 0                    # -1 down, +1 up, 0 unknown or both (B31)
    record_word: str | None = None


def hints(text: str, data: dict | None = None) -> Hints:
    data = data or load()
    h = Hints()
    h.hedges = found(text, data["hedges"])
    h.forecast = found(text, data["forecast_markers"])

    m12 = found(text, data["measures"]["12_month_change"])
    mm = found(text, data["measures"]["monthly_change"])
    low = text.lower()
    mm += [m.group(0) for rx in data["measures"].get("monthly_change_regex", [])
           for m in [re.search(rx, low)] if m]
    m12 += [m.group(0) for rx in data["measures"].get("12_month_change_regex", [])
            for m in [re.search(rx, low)] if m]
    if m12 and not mm:
        h.measure, h.measure_phrase = "12_month_change", m12[0]
    elif mm and not m12:
        h.measure, h.measure_phrase = "monthly_change", mm[0]

    for verb in data["change_verbs"]:
        m = _pattern(verb).search(low)
        # "økte renten med 0,25" / "satt ned med et kvart": "med"/"by" right before the amount,
        # not any later "med" ("hevet mye for å få bukt med den høye prisveksten").
        if m and re.search(r"(?<![\w-])(med|by)\s+(?:[-−]?\d|en |et |ett |one |a )", low[m.end():]):
            h.change_verb = verb
            break

    ind = data["indicators"]
    h.kpi_jae = bool(found(text, ind["kpi_jae"]))
    h.kpi_growth_noun = bool(found(text, ind["kpi_growth_nouns"])) and not h.kpi_jae
    h.kpi_explicit = (bool(found(text, ind["kpi_explicit"])) or h.kpi_growth_noun) and not h.kpi_jae
    h.inflation_generic = bool(found(text, ind["inflation_generic"]))
    h.prices_generic = bool(found(text, ind["prices_generic"]))
    for key, words in data["out_of_scope"].items():
        if found(text, words):
            h.out_of_scope = key
            break
    for key, patterns in ({} if h.out_of_scope else data.get("out_of_scope_regex", {})).items():
        hits = [rx for rx in patterns if re.search(rx, low)]
        if hits:
            # Only "prisene på X" names its subject outright; a compound word may be a cause.
            h.out_of_scope = key
            h.out_of_scope_specific = any("(på|for)" in rx for rx in hits) or key != "sub_index"
            break
    pw = found(text, data.get("points_words", []))
    h.points = pw[0] if pw else None
    down = bool(found(text, data.get("direction_down", [])))
    up = bool(found(text, data.get("direction_up", [])))
    h.direction = -1 if down and not up else (1 if up and not down else 0)
    rd = found(text, data.get("rate_decision_markers", []))
    h.rate_decision = rd[0] if rd else None
    rw = found(text, data["record_words"])
    h.record_word = rw[0] if rw else None
    return h


def review(raw: dict, data: dict | None = None) -> dict:
    """Return a corrected copy of one extracted claim dict, with overrides noted."""
    c = dict(raw)
    labels = list(c.get("labels") or [])
    notes = [c["notes"]] if isinstance(c.get("notes"), str) and c["notes"] else []
    h = hints(c.get("source_text", ""), data)

    def override(field_name: str, value, why: str) -> None:
        if c.get(field_name) != value:
            notes.append(f"Phrase tables: {field_name} set to {value!r} "
                         f"(was {c.get(field_name)!r}) because of {why}.")
            c[field_name] = value
            if "lexicon_override" not in labels:
                labels.append("lexicon_override")

    general = h.kpi_explicit or h.kpi_jae or h.inflation_generic or h.prices_generic
    policy_word = c.get("indicator") == "policy_rate" and bool(
        found(c.get("source_text", ""), (data or load())["indicators"]["policy_rate"]))
    if h.out_of_scope == "sub_index" and general and not h.out_of_scope_specific:
        pass  # a sub-index named as the cause of a KPI move; the claim is still KPI (B25)
    elif h.out_of_scope == "other_rate" and policy_word:
        pass  # "styringsrenten" named too; another rate is context, not the claim
    elif h.out_of_scope and c.get("status") in ("checkable", "ambiguous"):
        override("status", "out_of_scope", f"'{h.out_of_scope}' words")
        c["indicator"] = h.out_of_scope
    if c.get("status") == "checkable" and h.forecast:
        override("status", "forecast", f"forecast marker '{h.forecast[0]}'")
    if h.record_word and c.get("stated_value") in (None, ""):
        override("status", "no_figure", f"record word '{h.record_word}'")
    if h.hedges:
        override("hedged", True, f"hedge word '{h.hedges[0]}'")

    if c.get("status") == "checkable":
        if h.kpi_jae and c.get("indicator") in ("kpi", "kpi_jae", None):
            override("indicator", "kpi_jae", "a core-inflation phrase")
        if c.get("indicator") in ("policy_rate", "eurnok") and h.change_verb:
            override("measure", "change", f"change verb '{h.change_verb}'")
        elif c.get("indicator") in ("kpi", "kpi_jae") and h.points:
            # "Tolvmånedersveksten steg 1,3 prosentpoeng": a change in the rate (B27)
            override("measure", "change", f"'{h.points}'")
            override("unit", "percentage_points", f"'{h.points}'")
        elif c.get("indicator") in ("kpi", "kpi_jae") and h.measure:
            override("measure", h.measure, f"'{h.measure_phrase}'")
        if c.get("indicator") == "policy_rate" and h.rate_decision and "rate_decision" not in labels:
            labels.append("rate_decision")

    c["labels"] = labels
    if notes:
        c["notes"] = " ".join(notes)
    return c
