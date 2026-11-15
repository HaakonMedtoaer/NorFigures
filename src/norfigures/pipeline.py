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
