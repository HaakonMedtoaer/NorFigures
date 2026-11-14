"""Command-line entry point.

Weekend 1 ships `latest`. `check` arrives in weekends 2 and 3.
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .fetch import latest
from .ledger import LedgerError, load
from .net import Client, NetError
from .sources.base import SourceError

EXIT_OK = 0
EXIT_BAD_INPUT = 3


def cmd_latest(args) -> int:
    series = load()
    client = Client.from_env(offline=args.offline)
    rows = []
    for s in series.values():
        obs = latest(client, s)
        if obs is None:
            print(f"error: {s.id} returned no observations", file=sys.stderr)
            return EXIT_BAD_INPUT
        rows.append((s.id, obs.period, f"{obs.value}", s.unit, s.ref, obs.retrieved_at))

    headers = ("series", "period", "value", "unit", "source", "retrieved_at")
    widths = [max(len(str(r[i])) for r in [headers, *rows]) for i in range(len(headers))]
    line = "  ".join("{:<%d}" % w for w in widths)
    print(line.format(*headers))
    print(line.format(*("-" * w for w in widths)))
    for r in rows:
        print(line.format(*r))
    if args.offline:
        print("\n(offline: values replayed from tests/recorded/, not fetched now)")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="norfigures",
                                description="Verify Norwegian economic figures against SSB and Norges Bank.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    pl = sub.add_parser("latest", help="print the latest official value for each ledger series")
    pl.add_argument("--offline", action="store_true", help="replay recorded API responses")
    pl.set_defaults(func=cmd_latest)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (NetError, SourceError, LedgerError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_BAD_INPUT
