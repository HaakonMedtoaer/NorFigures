"""Command-line entry point.

    norfigures latest [--offline]
    norfigures check --claims FILE|- [--published YYYY-MM-DD] [--format table|json]
                     [--offline] [--log PATH]

`check` on raw text (with the extractor and mapper agents) arrives in weekend 3.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from . import __version__
from .claims import SchemaError, parse_json
from .events import RunLog, new_run_id
from .fetch import latest
from .ledger import LedgerError, load
from .net import REPO_ROOT, Client, NetError
from .pipeline import verify_claims
from .report import EXIT_BAD_INPUT, AccountingError, exit_code, render_json, render_table
from .sources.base import SourceError
from .verifier import ProvenanceError

EXIT_OK = 0


class InputError(Exception):
    """Unreadable, empty or non-text input. Exit code 3."""


def read_input(path: str) -> str:
    raw = sys.stdin.buffer.read() if path == "-" else _read_file(path)
    if b"\x00" in raw:
        raise InputError(f"{path}: looks like a binary file, expected UTF-8 text")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise InputError(f"{path}: not valid UTF-8 text ({e.reason})") from e
    if not text.strip():
        raise InputError(f"{path}: input is empty")
    return text


def _read_file(path: str) -> bytes:
    try:
        return Path(path).read_bytes()
    except OSError as e:
        raise InputError(f"cannot read {path}: {e.strerror or e}") from e


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


def cmd_check(args) -> int:
    if not args.claims:
        print("error: checking raw text needs the extractor and mapper agents (weekend 3).\n"
              "For now, pass hand-written claims with --claims FILE.", file=sys.stderr)
        return EXIT_BAD_INPUT
    text = read_input(args.claims)
    try:
        data = parse_json(text)
    except ValueError as e:
        raise InputError(f"{args.claims}: not valid JSON ({e})") from e
    published = _parse_date(args.published) if args.published else None

    run_id = new_run_id()
    log_path = Path(args.log) if args.log else REPO_ROOT / "runs" / f"{run_id}.jsonl"
    log = RunLog(run_id, None if args.log == "none" else log_path)
    log.emit("load", "ok", source=args.claims, published=args.published, offline=args.offline)

    series = load()
    outcome = verify_claims(data, Client.from_env(offline=args.offline), series,
                            published=published, log=log)
    code = exit_code(outcome.results)
    if args.format == "json":
        print(render_json(outcome.results, outcome.run_id))
    else:
        print(render_table(outcome.results, series))
        if args.offline:
            print("(offline: official values replayed from recorded API responses)")
    log.emit("report", "ok", exit_code=code)
    return code


def _parse_date(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError as e:
        raise InputError(f"--published must be YYYY-MM-DD, got {text!r}") from e


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="norfigures",
                                description="Verify Norwegian economic figures against SSB and Norges Bank.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    pl = sub.add_parser("latest", help="print the latest official value for each ledger series")
    pl.add_argument("--offline", action="store_true", help="replay recorded API responses")
    pl.set_defaults(func=cmd_latest)

    pc = sub.add_parser("check", help="verify claims against the official sources")
    pc.add_argument("--claims", metavar="FILE", help="JSON claims file, or - for stdin")
    pc.add_argument("--published", metavar="YYYY-MM-DD", help="publication date of the text")
    pc.add_argument("--format", choices=("table", "json"), default="table")
    pc.add_argument("--offline", action="store_true", help="replay recorded API responses")
    pc.add_argument("--log", metavar="PATH",
                    help="event log path (default runs/<run_id>.jsonl; 'none' to disable)")
    pc.set_defaults(func=cmd_check)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except SchemaError as e:
        print(f"error: failed extraction: {e}", file=sys.stderr)
    except (InputError, NetError, SourceError, LedgerError) as e:
        print(f"error: {e}", file=sys.stderr)
    except (ProvenanceError, AccountingError) as e:
        print(f"error: guardrail tripped: {e}", file=sys.stderr)
    return EXIT_BAD_INPUT
