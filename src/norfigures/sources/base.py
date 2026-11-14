"""Shared types for source adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


class SourceError(Exception):
    """The source answered, but not in a shape we understand. Exit code 3."""


@dataclass(frozen=True)
class Observation:
    """One official value, with enough provenance to show where it came from.

    `value` is a Decimal parsed from the source's own text, so the number of
    decimals the source published is preserved for the rounding rule.
    """

    source: str          # "ssb" | "norges_bank"
    series_id: str       # ledger key, e.g. "kpi_12m"
    period: str          # "2026-10" (month) or "2026-11-13" (day)
    value: Decimal
    url: str             # the exact GET that produced it
    retrieved_at: str
    dims: dict = field(default_factory=dict)
