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

SOURCES = ("ssb", "norges_bank")
_REQUIRED = {
    "ssb": ("table", "selection"),
    "norges_bank": ("flow", "key"),
}


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

    @property
    def ref(self) -> str:
        """Human-readable reference for reports."""
        if self.source == "ssb":
            sel = ", ".join(f"{k}={v}" for k, v in self.selection.items())
            return f"SSB table {self.table} ({sel})"
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
        try:
            out[sid] = Series(id=sid, **spec)
        except TypeError as e:
            raise LedgerError(f"series {sid}: {e}") from e
    return out
