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
                 end: str | None = None, last_n: int | None = None) -> list[Observation]:
    if series.source == "ssb":
        return ssb.fetch(client, series.id, series.table, series.selection,
                         start=start, end=end, last_n=last_n)
    if series.source == "norges_bank":
        return norges_bank.fetch(client, series.id, series.flow, series.key,
                                 start=start, end=end, last_n=last_n)
    raise ValueError(f"unknown source {series.source!r}")


def latest(client: Client, series: Series) -> Observation | None:
    obs = fetch_series(client, series, last_n=1)
    return obs[-1] if obs else None
