"""Reports (table for people, JSON for machines) and exit codes."""

from __future__ import annotations

import json
import textwrap

from .ledger import Series
from .verifier import CANNOT_VERIFY, MATCHED, MISMATCHED, ClaimResult

EXIT_ALL_MATCHED = 0
EXIT_MISMATCH = 1
EXIT_UNVERIFIED = 2
EXIT_BAD_INPUT = 3


class AccountingError(Exception):
    """The summary counts do not add up. A bug, never a data problem."""


def summarize(results: list[ClaimResult]) -> dict:
    s = {
        "claims_found": len(results),
        "matched": sum(r.verdict == MATCHED for r in results),
        "mismatched": sum(r.verdict == MISMATCHED for r in results),
        "cannot_verify": sum(r.verdict == CANNOT_VERIFY for r in results),
    }
    if s["matched"] + s["mismatched"] + s["cannot_verify"] != s["claims_found"]:
        raise AccountingError(f"counts do not add up: {s}")
    return s


def exit_code(results: list[ClaimResult]) -> int:
    """A mismatch outranks an unverifiable claim; nothing checked is never a pass."""
    s = summarize(results)
    if s["mismatched"]:
        return EXIT_MISMATCH
    if s["cannot_verify"] or s["claims_found"] == 0:
        return EXIT_UNVERIFIED
    return EXIT_ALL_MATCHED


def _official(res: ClaimResult) -> str:
    r = res.chosen
    if r is None or not r.has_data:
        return "n/a"
    if r.kind == "range" and r.low != r.high:
        return f"{r.low}-{r.high}"
    return str(r.official_value)


def _source(res: ClaimResult, series: dict[str, Series]) -> str:
    """Short provenance: source, series, the period actually used, and the table/key."""
    r = res.chosen
    if r is None:
        return "none"
    s = series[r.series_id]
    period = r.observations[-1].period if (r.kind == "point" and r.observations) else r.period
    if s.source == "ssb":
        return f"SSB, {s.id}, {period}, table {s.table}"
    return f"Norges Bank, {s.id}, {period}, {s.flow}/{s.key}"


def _verdict_text(res: ClaimResult) -> str:
    text = res.verdict.replace("_", " ").upper()
    reasons = [l for l in res.labels if l in (
        "forecast_not_checkable", "no_figure", "out_of_scope", "period_missing", "no_data",
        "incomplete_data", "mapping_mismatch", "annual_not_supported", "ambiguous")]
    if res.verdict == CANNOT_VERIFY and reasons:
        text += f" ({reasons[0].replace('_', ' ')})"
    return text


def render_table(results: list[ClaimResult], series: dict[str, Series], width: int = 100) -> str:
    rows = []
    for i, res in enumerate(results, 1):
        c = res.claim
        stated = "n/a" if c.stated_value is None else str(c.stated_value)
        if c.hedged:
            stated = "~" + stated
        rows.append([str(i), _clip(c.source_text, 38), stated, _official(res),
                     _verdict_text(res), _source(res, series)])
    headers = ["#", "Claim", "Stated", "Official", "Verdict", "Source"]
    widths = [max(len(r[k]) for r in [headers, *rows]) for k in range(len(headers))]
    fmt = "  ".join("{:<%d}" % w for w in widths)
    lines = [fmt.format(*headers), fmt.format(*("-" * w for w in widths))]
    lines += [fmt.format(*r) for r in rows]

    notes = []
    for i, res in enumerate(results, 1):
        extra = [l for l in res.labels]
        text = " ".join(n if n.endswith(".") else n + "." for n in res.notes)
        if extra or text:
            label_part = f"[{', '.join(extra)}] " if extra else ""
            notes.append(textwrap.fill(f"{i}. {label_part}{text}", width=width,
                                       subsequent_indent="   "))
    if notes:
        lines += ["", "Notes:"] + notes

    s = summarize(results)
    lines += ["", f"Claims found: {s['claims_found']} | matched: {s['matched']} | "
                  f"mismatched: {s['mismatched']} | could not verify: {s['cannot_verify']}"]
    if s["claims_found"] == 0:
        lines.append("Nothing was checked. This is not a pass.")
    return "\n".join(lines)


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def to_json(results: list[ClaimResult], run_id: str) -> dict:
    """Numbers are strings so published precision survives ("4.0" stays "4.0")."""
    out = []
    for res in results:
        c, r = res.claim, res.chosen
        out.append({
            "id": c.id,
            "source_text": c.source_text,
            "status": c.status,
            "indicator": c.indicator,
            "measure": c.measure,
            "period": res.period or c.period,
            "period_inferred": res.period_inferred,
            "unit": c.unit,
            "stated_value": None if c.stated_value is None else str(c.stated_value),
            "hedged": c.hedged,
            "official_value": _official(res) if r and r.has_data else None,
            "retrieved_at": r.retrieved_at if r else None,
            "verdict": res.verdict,
            "labels": res.labels,
            "notes": " ".join(res.notes),
            "readings": [{
                "series_id": x.series_id, "period": x.period, "kind": x.kind,
                "official_value": None if x.official_value is None else str(x.official_value),
                "low": None if x.low is None else str(x.low),
                "high": None if x.high is None else str(x.high),
                "matched": x.matched, "url": x.url, "retrieved_at": x.retrieved_at,
            } for x in res.readings],
        })
    return {"run_id": run_id, "claims": out, "summary": summarize(results),
            "exit_code": exit_code(results)}


def render_json(results: list[ClaimResult], run_id: str) -> str:
    return json.dumps(to_json(results, run_id), ensure_ascii=False, indent=2)
