"""Read canonical series definitions from facts/ledger.md.

The ledger is the single source of truth: the `json series` block in it is
parsed here, so a series ID never has to be written twice.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .net import REPO_ROOT

LEDGER_PATH = REPO_ROOT / "facts" / "ledger.md"

_BLOCK = re.compile(r"```json series\n(.*?)\n```", re.S)

SOURCES = ("ssb", "norges_bank", "nav")
_REQUIRED = {
    "ssb": ("table", "selection"),
    "norges_bank": ("flow", "key"),
    "nav": ("table", "selection"),   # table: NAV's file code (HL050); selection: sheet and row
}


def _next_month(month: str) -> str:
    y, m = int(month[:4]), int(month[5:7])
    return f"{y + 1:04d}-01" if m == 12 else f"{y:04d}-{m + 1:02d}"


class LedgerError(Exception):
    """The ledger is missing or malformed. Exit code 3."""


@dataclass(frozen=True)
class Series:
    id: str
    indicator: str
    measure: str
    unit: str
    concept: str
    source: str
    frequency: str
    confirmed: str
    table: str | None = None
    selection: dict | None = None
    flow: str | None = None
    key: str | None = None
    # Older periods read from other tables: [{"until": "YYYY-MM", "table", "selection"}],
    # oldest last-period first. Periods after the last `until` use table/selection (B24).
    history: tuple = ()
    # Monthly series: month M is published between these days of month M+1 (inclusive).
    # Used to infer a missing period (D14): inside the window both months are checked.
    release_window: tuple | None = None
    # Months after M in which month M is published: 1 for SSB, 0 for NAV, which
    # publishes a month's figures late in that same month (D20).
    release_month_offset: int = 1
    # Breaks in the series: [["YYYY-MM", "YYYY-MM"], ...]. A change between two
    # months is not computed when either month is inside a break (D20).
    breaks: tuple = ()

    def in_break(self, month: str) -> bool:
        return any(lo <= month <= hi for lo, hi in self.breaks)

    def segments(self, start: str, end: str) -> list[tuple[str, str, str, dict]]:
        """Split a YYYY-MM range into (start, end, table, selection) per source table."""
        out, lo = [], start
        for h in self.history:
            if lo > end:
                break
            if lo <= h["until"]:
                hi = min(end, h["until"])
                out.append((lo, hi, h["table"], h["selection"]))
                lo = _next_month(hi)
        if lo <= end:
            out.append((lo, end, self.table, self.selection))
        return out

    @property
    def ref(self) -> str:
        """Human-readable reference for reports."""
        if self.source == "ssb":
            sel = ", ".join(f"{k}={v}" for k, v in self.selection.items())
            return f"SSB table {self.table} ({sel})"
        if self.source == "nav":
            return f"NAV table {self.table} (row {self.selection['row']!r})"
        return f"Norges Bank {self.flow}/{self.key}"


def load(path: Path | None = None) -> dict[str, Series]:
    path = Path(path or LEDGER_PATH)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise LedgerError(f"cannot read ledger {path}: {e}") from e
    blocks = _BLOCK.findall(text)
    if len(blocks) != 1:
        raise LedgerError(f"ledger must contain exactly one ```json series block, found {len(blocks)}")
    try:
        raw = json.loads(blocks[0])
    except json.JSONDecodeError as e:
        raise LedgerError(f"series block is not valid JSON: {e}") from e

    out = {}
    for sid, spec in raw.items():
        source = spec.get("source")
        if source not in SOURCES:
            raise LedgerError(f"series {sid}: unknown source {source!r}")
        missing = [f for f in _REQUIRED[source] if not spec.get(f)]
        if missing:
            raise LedgerError(f"series {sid}: missing {missing}")
        hist = spec.get("history", [])
        if hist and source != "ssb":
            raise LedgerError(f"series {sid}: history is only supported for SSB series")
        for h in hist:
            if not (isinstance(h, dict) and re.fullmatch(r"\d{4}-\d{2}", str(h.get("until", "")))
                    and h.get("table") and isinstance(h.get("selection"), dict)):
                raise LedgerError(f"series {sid}: each history entry needs until (YYYY-MM), table, selection")
        if [h["until"] for h in hist] != sorted(h["until"] for h in hist):
            raise LedgerError(f"series {sid}: history must be in order of 'until'")
        rw = spec.get("release_window")
        if rw is not None:
            if not (isinstance(rw, list) and len(rw) == 2 and all(isinstance(d, int) for d in rw)
                    and 1 <= rw[0] <= rw[1] <= 31 and spec.get("frequency") == "M"):
                raise LedgerError(f"series {sid}: release_window must be [first_day, last_day] "
                                  "on a monthly series")
            rw = tuple(rw)
        off = spec.get("release_month_offset", 1)
        if off not in (0, 1):
            raise LedgerError(f"series {sid}: release_month_offset must be 0 or 1")
        brk = spec.get("breaks", [])
        if not all(isinstance(b, list) and len(b) == 2 and all(re.fullmatch(r"\d{4}-\d{2}", str(x)) for x in b)
                   and b[0] <= b[1] for b in brk):
            raise LedgerError(f"series {sid}: breaks must be [[\"YYYY-MM\", \"YYYY-MM\"], ...]")
        if source == "nav":
            sel = spec.get("selection") or {}
            if not (isinstance(sel.get("sheet"), list) and sel["sheet"] and isinstance(sel.get("row"), str)):
                raise LedgerError(f"series {sid}: NAV selection needs sheet (list of words) and row")
        spec = dict(spec, history=tuple(hist), release_window=rw,
                    breaks=tuple(tuple(b) for b in brk))
        try:
            out[sid] = Series(id=sid, **spec)
        except TypeError as e:
            raise LedgerError(f"series {sid}: {e}") from e
    return out
