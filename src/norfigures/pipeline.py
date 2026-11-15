"""Glue: claims in, verified results out, with every step logged.

Weekend 2 takes claims that were written by hand (or recorded from the
agents). Weekend 3 puts the extractor and mapper in front of this.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .claims import Claim, SchemaError, validate
from .events import RunLog
from .ledger import Series
from .lexicon import review
from .mapper import map_claim
from .net import Client
from .verifier import ClaimResult, Run, check_provenance, verify_claim


@dataclass
class Outcome:
    run_id: str
    results: list[ClaimResult]


def verify_claims(data: object, client: Client, series: dict[str, Series],
                  published: date | None = None, today: date | None = None,
                  log: RunLog | None = None) -> Outcome:
    log = log or RunLog()
    today = today or date.today()
    try:
        claims: list[Claim] = validate(data, series)
    except SchemaError as e:
        log.emit("validate", "failed", problems=e.problems)
        raise
    log.emit("validate", "ok", claims=len(claims))

    run = Run(client, series, log)
    results = []
    for c in claims:
        res = verify_claim(c, run, published, today)
        log.emit("compare", res.verdict, c.id, labels=res.labels,
                 readings=[{"series_id": r.series_id, "period": r.period,
                            "official": str(r.official_value) if r.official_value is not None else None,
                            "matched": r.matched} for r in res.readings])
        results.append(res)

    check_provenance(results, run)
    return Outcome(log.run_id, results)


@dataclass
class TextOutcome(Outcome):
    extraction: object = None   # agents.extractor.Extraction


def prepare(extracted: list[dict], series: dict[str, Series], log: RunLog) -> list[dict]:
    """Phrase-table review, then deterministic mapping, for extracted claims."""
    out = []
    for raw in extracted:
        c = review(raw)
        if c["status"] == "out_of_scope" and not c.get("indicator"):
            c["indicator"] = "unknown"
        ids, note = map_claim(c, series)
        if c["status"] == "checkable" and not ids:
            c["status"] = "ambiguous"
            c["labels"] = [*c.get("labels", []), "unmapped"]
        if note:
            c["notes"] = (c.get("notes", "") + " " + note).strip()
        c["mappings"] = [{"series_id": i} for i in ids]
        log.emit("map", "ok" if ids else "unmapped", c["id"], mappings=ids,
                 status=c["status"], labels=c.get("labels", []))
        out.append(c)
    return out


def check_text(text: str, client: Client, series: dict[str, Series], agent_mode: str,
               published: date | None = None, today: date | None = None,
               log: RunLog | None = None) -> TextOutcome:
    """Full loop: extractor agent -> phrase tables -> mapper -> verifier."""
    from .agents.extractor import ExtractionError, extract
    from .agents.llm import AgentError

    log = log or RunLog()
    pub = published.isoformat() if published else None
    try:
        ex = extract(text, pub, mode=agent_mode)
    except (ExtractionError, AgentError) as e:
        log.emit("extract", "failed", error=str(e))
        raise
    log.emit("extract", "ok", claims=len(ex.claims), model=ex.model, replayed=ex.replayed,
             input_tokens=ex.input_tokens, output_tokens=ex.output_tokens,
             cost_usd=round(ex.cost_usd, 6))
    claims = prepare(ex.claims, series, log)
    outcome = verify_claims(claims, client, series, published=published, today=today, log=log)
    return TextOutcome(outcome.run_id, outcome.results, ex)
