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
from .lexicon import matched_phrases, review
from .mapper import map_claim
from .net import Client
from .verifier import ClaimResult, ProvenanceError, Run, check_provenance, verify_claim


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
        chosen = res.chosen
        log.emit("compare", res.verdict, c.id, labels=res.labels,
                 source_text=c.source_text, claim_status=c.status,
                 stated=str(c.stated_value) if c.stated_value is not None else None,
                 chosen=chosen.series_id if chosen is not None else None,
                 readings=[{"series_id": r.series_id, "period": r.period,
                            "official": str(r.official_value) if r.official_value is not None else None,
                            "observed": r.observations[-1].period if r.observations else None,
                            "matched": r.matched} for r in res.readings])
        results.append(res)

    try:
        check_provenance(results, run)
    except ProvenanceError as e:
        log.emit("provenance", "failed", guardrail="provenance", error=str(e))
        raise
    log.emit("provenance", "ok",
             checked=sum(1 for r in results for x in r.readings if x.has_data))
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
        if ids:
            _align_measure(c, series[ids[0]])
        if note:
            c["notes"] = (c.get("notes", "") + " " + note).strip()
        c["mappings"] = [{"series_id": i} for i in ids]
        log.emit("map", "ok" if ids else "unmapped", c["id"], mappings=ids,
                 claim_status=c["status"], labels=c.get("labels", []),
                 source_text=c.get("source_text"), stated=c.get("stated_value"),
                 indicator=c.get("indicator"), measure=c.get("measure"), period=c.get("period"),
                 phrases=matched_phrases(c.get("source_text") or "", c.get("stated_value")))
        out.append(c)
    return out


def _align_measure(c: dict, canonical: Series) -> None:
    """The mapping rules (D12) decide the measure, not the extractor.

    Inflation is always a change (12-month or monthly), never a level; a rate or
    exchange rate is a level unless a change verb made it a change.
    """
    old = c.get("measure")
    if c.get("indicator") in ("kpi", "kpi_jae"):
        new = "change" if old == "change" else canonical.measure
    elif old in (None, "level", "change"):
        new = old or "level"
    else:
        new = "level"
    if new != old:
        c["measure"] = new
        if old is not None:
            c["notes"] = (c.get("notes", "") + f" Measure set to {new!r} by the mapping "
                          f"rules (D12); the extractor said {old!r}.").strip()
            c["labels"] = [*c.get("labels", []), "measure_from_rules"]


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
