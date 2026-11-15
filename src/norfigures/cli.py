"""Command-line entry point.

    norfigures latest [--offline]
    norfigures check FILE|-          [--published YYYY-MM-DD] [--format table|json]
                                     [--offline] [--log PATH]
    norfigures check --claims FILE|- (hand-written claims; no model involved)
    norfigures record-agents         (record extractor outputs for tests/cases)

Text input runs the extractor agent (needs `pip install 'norfigures[agents]'`
and an Anthropic API key), unless --offline replays a recorded output.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from . import __version__
from .claims import SchemaError, parse_json
from .events import RunLog, new_run_id
from .fetch import latest
from .ledger import LedgerError, load
from .net import REPO_ROOT, Client, NetError
from .pipeline import check_text, verify_claims
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
    if bool(args.input) == bool(args.claims):
        raise InputError("give either a text FILE (or -) or --claims FILE, not both or neither")
    published = _parse_date(args.published) if args.published else None
    source = args.claims or args.input
    text = read_input(source)

    run_id = new_run_id()
    log_path = Path(args.log) if args.log else REPO_ROOT / "runs" / f"{run_id}.jsonl"
    log = RunLog(run_id, None if args.log == "none" else log_path)
    log.emit("load", "ok", source=source, published=args.published, offline=args.offline,
             kind="claims" if args.claims else "text")

    series = load()
    client = Client.from_env(offline=args.offline)
    extraction = None
    if args.claims:
        try:
            data = parse_json(text)
        except ValueError as e:
            raise InputError(f"{source}: not valid JSON ({e})") from e
        outcome = verify_claims(data, client, series, published=published, log=log)
    else:
        outcome = check_text(text, client, series, _agent_mode(args.offline),
                             published=published, log=log)
        extraction = outcome.extraction

    code = exit_code(outcome.results)
    if args.format == "json":
        print(render_json(outcome.results, outcome.run_id))
    else:
        print(render_table(outcome.results, series))
        if extraction is not None:
            how = "replayed" if extraction.replayed else "live"
            print(f"Extractor: {extraction.model} ({how}), {extraction.input_tokens} in / "
                  f"{extraction.output_tokens} out tokens, about ${extraction.cost_usd:.4f}")
        if args.offline:
            print("(offline: official values replayed from recorded API responses)")
    log.emit("report", "ok", exit_code=code)
    return code


def _agent_mode(offline: bool) -> str:
    if offline:
        return "replay"
    return "record" if os.environ.get("NORFIGURES_RECORD") == "1" else "live"


def cmd_record_agents(args) -> int:
    """Run the extractor live on every fixture text and save its output."""
    from .agents.extractor import extract
    cases = sorted((REPO_ROOT / "tests" / "cases").glob("*.json"))
    total_in = total_out = 0
    cost = 0.0
    for p in cases:
        case = parse_json(p.read_text(encoding="utf-8"))
        ex = extract(case["text"], case.get("published"), mode="record")
        total_in += ex.input_tokens
        total_out += ex.output_tokens
        cost += ex.cost_usd
        print(f"{p.stem}: {len(ex.claims)} claims, {ex.input_tokens} in / {ex.output_tokens} out")
    print(f"\nRecorded {len(cases)} texts with {ex.model if cases else '-'}: "
          f"{total_in} input and {total_out} output tokens, about ${cost:.4f} in total, "
          f"${cost / max(len(cases), 1):.5f} per text.")
    return EXIT_OK


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

    pc = sub.add_parser("check", help="verify the figures in a text against the official sources")
    pc.add_argument("input", nargs="?", metavar="FILE", help="text file to check, or - for stdin")
    pc.add_argument("--claims", metavar="FILE", help="hand-written JSON claims instead of text")
    pc.add_argument("--published", metavar="YYYY-MM-DD", help="publication date of the text")
    pc.add_argument("--format", choices=("table", "json"), default="table")
    pc.add_argument("--offline", action="store_true", help="replay recorded API responses")
    pc.add_argument("--log", metavar="PATH",
                    help="event log path (default runs/<run_id>.jsonl; 'none' to disable)")
    pc.set_defaults(func=cmd_check)

    pr = sub.add_parser("record-agents",
                        help="run the extractor live on tests/cases and record its outputs")
    pr.set_defaults(func=cmd_record_agents)
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
    except Exception as e:  # agent errors are imported lazily
        if type(e).__name__ not in ("AgentError", "ExtractionError"):
            raise
        print(f"error: {e}", file=sys.stderr)
    return EXIT_BAD_INPUT
