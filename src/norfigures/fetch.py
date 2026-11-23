"""One entry point for fetching a ledger series, whatever the source.

The verifier (weekend 2) and the MCP server (weekend 3) both call this, so
there is exactly one path from a series ID to an official number.
"""

from __future__ import annotations

from .ledger import Series
from .net import Client
from .sources import norges_bank, ssb
from .sources.base import Observation


def fetch_series(client: Client, series: Series, start: str | None = None,
                 end: str | None = None, last_n: int | None = None,
                 same_table: bool = False) -> list[Observation]:
    """Fetch one series. `same_table` takes the whole range from the table that holds
    the last period, so a change between two months is computed within one table,
    as SSB does (B33)."""
    if series.source == "ssb":
        if same_table and series.history and (start or end):
            lo, hi = start or end, end or start
            _, _, table, selection = series.segments(hi, hi)[0]
            return ssb.fetch(client, series.id, table, selection, start=lo, end=hi)
        if not (start or end) or not series.history:
            return ssb.fetch(client, series.id, series.table, series.selection,
                             start=start, end=end, last_n=last_n)
        # Periods before a rebase come from the table that holds them as published (B24).
        out: list[Observation] = []
        for lo, hi, table, selection in series.segments(start or end, end or start):
            out += ssb.fetch(client, series.id, table, selection, start=lo, end=hi)
        return out
    if series.source == "norges_bank":
        return norges_bank.fetch(client, series.id, series.flow, series.key,
                                 start=start, end=end, last_n=last_n)
    raise ValueError(f"unknown source {series.source!r}")


def latest(client: Client, series: Series) -> Observation | None:
    """The newest period that has a value. A centred series (AKU 3-month average, B45)
    lists its newest month as missing until the next release, so look back a little."""
    obs = fetch_series(client, series, last_n=1)
    if not obs:
        obs = fetch_series(client, series, last_n=3)
    return obs[-1] if obs else None
