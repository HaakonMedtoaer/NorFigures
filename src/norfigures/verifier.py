"""Deterministic verification. No model is involved anywhere in this module.

Each claim is resolved to one or more readings (series x period), each reading
is fetched through the run (so every number has provenance), and compared
under the decided rules in docs/decisions.md (D4 to D16).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from . import periods
from .claims import Claim
from .events import RunLog
from .fetch import fetch_series
from .ledger import Series
from .net import Client, HostNotAllowed
from .sources.base import Observation

MATCHED, MISMATCHED, CANNOT_VERIFY = "matched", "mismatched", "cannot_verify"

# How far back to look for the last business-day observation on or before a date.
DAILY_LOOKBACK_DAYS = 14
# How far after a rate decision's date to look for the rate in force (B35).
DECISION_WINDOW_DAYS = 7


class ProvenanceError(Exception):
    """An official value did not come from a fetch in this run. Exit code 3."""


# --------------------------------------------------------------------------- run


def _fetch_detail(s: Series, start: str, end: str, obs: list[Observation]) -> dict:
    """Where a fetch went, for the run log and the flow map: source, table or key."""
    if s.source == "ssb":
        tables = list(dict.fromkeys(o.dims.get("_table") for o in obs if o.dims.get("_table")))
        ref = "table " + " + ".join(tables or [s.table])
    else:
        ref = f"{s.flow}/{s.key}"
    return {"series_id": s.id, "source": s.source, "ref": ref, "concept": s.concept,
            "start": start, "end": end}


class Run:
    """Holds the client, the ledger and every observation fetched in this run."""

    def __init__(self, client: Client, series: dict[str, Series], log: RunLog | None = None):
        self.client = client
        self.series = series
        self.log = log or RunLog()
        self._registry: set[int] = set()
        self._cache: dict[tuple, list[Observation]] = {}

    def fetch(self, s: Series, start: str, end: str, claim_id: str | None = None,
              same_table: bool = False) -> list[Observation]:
        key = (s.id, start, end, same_table)
        if key not in self._cache:
            try:
                obs = fetch_series(self.client, s, start=start, end=end, same_table=same_table)
            except Exception as e:
                self.log.emit("fetch", "failed", claim_id, **_fetch_detail(s, start, end, []),
                              error=str(e), guardrail="host_not_allowed"
                              if isinstance(e, HostNotAllowed) else None)
                raise
            self._registry.update(id(o) for o in obs)
            self._cache[key] = obs
            self.log.emit("fetch", "ok", claim_id, **_fetch_detail(s, start, end, obs),
                          observations=len(obs), url=obs[0].url if obs else None)
        else:
            self.log.emit("fetch", "cached", claim_id,
                          **_fetch_detail(s, start, end, self._cache[key]))
        return self._cache[key]

    def is_registered(self, obs: Observation) -> bool:
        return id(obs) in self._registry


# ---------------------------------------------------------------------- results


@dataclass
class Reading:
    series_id: str
    period: str
    kind: str                          # "point" | "range" | "change"
    official_value: Decimal | None = None
    low: Decimal | None = None
    high: Decimal | None = None
    observations: list[Observation] = field(default_factory=list)
    matched: bool | None = None
    note: str = ""

    @property
    def has_data(self) -> bool:
        return self.official_value is not None or self.low is not None

    @property
    def url(self) -> str | None:
        return self.observations[-1].url if self.observations else None

    @property
    def retrieved_at(self) -> str | None:
        return self.observations[-1].retrieved_at if self.observations else None


@dataclass
class ClaimResult:
    claim: Claim
    verdict: str
    labels: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    readings: list[Reading] = field(default_factory=list)
    period: str | None = None
    period_inferred: bool = False

    @property
    def chosen(self) -> Reading | None:
        """The reading shown as 'official': the first match, else the canonical one."""
        for r in self.readings:
            if r.matched:
                return r
        for r in self.readings:
            if r.has_data:
                return r
        return self.readings[0] if self.readings else None

    def add_label(self, label: str) -> None:
        if label not in self.labels:
            self.labels.append(label)


# --------------------------------------------------------------------- compare


def decimals_of(d: Decimal) -> int:
    return max(0, -d.as_tuple().exponent)


def round_like(official: Decimal, stated: Decimal) -> Decimal:
    """Round the official value half-up to the stated number of decimals (D8)."""
    return official.quantize(Decimal(1).scaleb(-decimals_of(stated)), rounding=ROUND_HALF_UP)


def tolerance(stated: Decimal, hedged: bool) -> Decimal:
    """Zero, or one unit in the last stated digit for hedged figures (D10)."""
    return Decimal(1).scaleb(-decimals_of(stated)) if hedged else Decimal(0)


def compare_point(stated: Decimal, official: Decimal, hedged: bool) -> bool:
    return abs(round_like(official, stated) - stated) <= tolerance(stated, hedged)


def compare_range(stated: Decimal, low: Decimal, high: Decimal, hedged: bool) -> bool:
    """Matched if the stated value lies within the period's low and high (D9)."""
    tol = tolerance(stated, hedged)
    return round_like(low, stated) - tol <= stated <= round_like(high, stated) + tol


# ---------------------------------------------------------------------- verify


def verify_claim(claim: Claim, run: Run, published: date | None, today: date) -> ClaimResult:
    res = ClaimResult(claim, CANNOT_VERIFY, labels=list(claim.labels))
    if claim.notes:
        res.notes.append(claim.notes)

    def cannot(label: str, note: str) -> ClaimResult:
        res.verdict = CANNOT_VERIFY
        res.add_label(label)
        res.notes.append(note)
        return res

    # 1. Status set by the extractor.
    if claim.status == "forecast":
        return cannot("forecast_not_checkable", "Forecast or expectation; published data cannot confirm it.")
    if claim.status == "no_figure":
        return cannot("no_figure", "No number to check.")
    if claim.status == "out_of_scope":
        if claim.indicator == "sub_index":
            return cannot("out_of_scope", "A sub-index such as food or electricity prices is part "
                                          "of KPI, not KPI itself; it is not covered yet.")
        return cannot("out_of_scope", f"Indicator '{claim.indicator}' is not covered yet.")
    if not claim.mappings:
        return cannot("ambiguous", "The claim could not be tied to a series.")
    if claim.stated_value is None:
        return cannot("no_figure", "No number to check.")

    # 2. Resolve the period(s).
    reference = published or today
    if claim.period:
        if periods.period_start(claim.period) > reference:
            return cannot("forecast_not_checkable",
                          f"Period {claim.period} is after {reference.isoformat()}; it cannot be published yet.")
        if periods.kind(claim.period) == "year":
            return cannot("annual_not_supported",
                          "Annual figures are not covered yet; only monthly and daily values.")
        candidates = [claim.period]
    elif published is None:
        return cannot("period_missing", "No period in the claim and no --published date to infer one from.")
    else:
        res.period_inferred = True
        res.add_label("period_inferred")
        candidates = None  # per series below

    # 3. Build and evaluate readings.
    for i, sid in enumerate(claim.mappings):
        s = run.series[sid]
        # The claim's measure describes the canonical (first) reading. Alternative
        # readings exist precisely because the measure is uncertain (D4, D12), so
        # only their unit is checked.
        problem = _mapping_problem(claim, s, check_measure=(i == 0))
        if problem:
            res.add_label("mapping_mismatch")
            res.notes.append(f"{sid}: {problem}")
            continue
        if candidates is None:
            if s.frequency == "M":
                plist = periods.infer_monthly(published, s.release_window)
            else:
                plist = [published.isoformat()]
        else:
            plist = candidates
        for p in plist:
            reading = _read(claim, s, p, run)
            res.readings.append(reading)

    if not res.readings:
        res.verdict = CANNOT_VERIFY
        return res

    if claim.measure == "change" and claim.unit in (None, "percent") and \
            any(run.series[r.series_id].unit == "percent" and run.series[r.series_id].frequency != "M"
                for r in res.readings):
        res.add_label("unit_assumed")
        res.notes.append("A change in a rate is read as percentage points (D11).")
    if claim.hedged:
        res.add_label("approximate")

    if len(claim.mappings) > 1:
        res.add_label("ambiguous_measure")
    if len({r.period for r in res.readings}) > 1:
        res.add_label("period_ambiguous")
    res.period = res.chosen.period if res.chosen else None

    _decide(res, run)
    if res.verdict == MISMATCHED and "unemployment_source_unnamed" in claim.labels:
        # "Ledigheten var 2,1 prosent" may be NAV's registered rate, which is not
        # covered yet; without an AKU word, a mismatch would be a guess (D16, B43).
        res.verdict = CANNOT_VERIFY
        res.notes.append("Does not match AKU, and the text does not say AKU: it may be NAV's "
                         "registered unemployment, which is not covered yet.")
    return res


def _mapping_problem(claim: Claim, s: Series, check_measure: bool = True) -> str | None:
    if not check_measure:
        pass
    elif claim.measure == "change":
        if s.frequency == "M" and claim.unit not in (None, "percentage_points"):
            return "a change in an inflation rate is in percentage points"
    elif claim.measure != s.measure:
        return f"claim measure '{claim.measure}' does not match series measure '{s.measure}'"
    if claim.unit == "nok_per_eur" and s.unit != "nok_per_eur":
        return f"claim unit '{claim.unit}' does not match series unit '{s.unit}'"
    if claim.unit == "percent" and s.unit == "nok_per_eur":
        return "claim is in percent but the series is an exchange rate"
    return None


def _read(claim: Claim, s: Series, period: str, run: Run) -> Reading:
    k = periods.kind(period)
    if s.frequency == "M" and claim.measure == "change":
        # Change in the rate itself, in points (B27): this month's rate minus last month's.
        month = period if k == "month" else period[:7]
        prev = periods.add_months(month, -1)
        obs = run.fetch(s, prev, month, claim.id, same_table=True)
        r = Reading(s.id, month, "change")
        if len(obs) == 2 and obs[0].period == prev and obs[1].period == month:
            r.observations = [obs[0], obs[1]]
            r.official_value = obs[1].value - obs[0].value
            r.note = f"{s.concept}: {prev} {obs[0].value} -> {month} {obs[1].value}"
        else:
            r.note = f"{s.id} has no values for both {prev} and {month}"
        return r

    if s.frequency == "M":
        month = period if k == "month" else period[:7]
        obs = run.fetch(s, month, month, claim.id)
        r = Reading(s.id, month, "point", observations=obs[-1:])
        if obs:
            r.official_value = obs[-1].value
        else:
            r.note = f"{s.id} has no value for {month} yet"
        return r

    # Daily series (policy rate, EUR/NOK).
    if claim.measure == "change":
        start = periods.period_start(period)
        end = periods.parse_day(period) if k == "day" else periods.month_bounds(period)[1]
        obs = run.fetch(s, (start - timedelta(days=DAILY_LOOKBACK_DAYS)).isoformat(),
                        end.isoformat(), claim.id)
        before = [o for o in obs if o.period < start.isoformat()]
        upto = [o for o in obs if o.period <= end.isoformat()]
        r = Reading(s.id, period, "change")
        if before and upto:
            r.observations = [before[-1], upto[-1]]
            r.official_value = upto[-1].value - before[-1].value
            r.note = f"{before[-1].period}: {before[-1].value} -> {upto[-1].period}: {upto[-1].value}"
        else:
            r.note = f"not enough observations around {period}"
        return r

    if k == "day" and s.id == "policy_rate" and "rate_decision" in claim.labels:
        # A decision is announced the day after the meeting and takes effect the next
        # business day. Check the rate once it is in force: the rate a week after the
        # given date (meetings are about six weeks apart) (B29, revised in B35).
        d = periods.parse_day(period)
        until = d + timedelta(days=DECISION_WINDOW_DAYS)
        obs = run.fetch(s, (d - timedelta(days=DAILY_LOOKBACK_DAYS)).isoformat(), until.isoformat(), claim.id)
        r = Reading(s.id, period, "point")
        later = [o for o in obs if o.period > period]
        if later:
            r.observations = [later[-1]]
            r.official_value = later[-1].value
            r.note = (f"Rate decision: checked against the rate in force after it took effect, "
                      f"{later[-1].period}.")
        else:
            r.note = f"Rate decision on {period} is not yet in force in Norges Bank's data."
        return r

    if k == "day":
        d = periods.parse_day(period)
        obs = run.fetch(s, (d - timedelta(days=DAILY_LOOKBACK_DAYS)).isoformat(), d.isoformat(), claim.id)
        upto = [o for o in obs if o.period <= period]
        r = Reading(s.id, period, "point")
        if upto:
            r.observations = [upto[-1]]
            r.official_value = upto[-1].value
            if upto[-1].period != period:
                r.note = f"no observation on {period}; using the latest one before it, {upto[-1].period}"
        else:
            r.note = f"no observation on or before {period}"
        return r

    # A month on a daily series: compare with the month's low and high (D9).
    first, last = periods.month_bounds(period)
    obs = run.fetch(s, first.isoformat(), last.isoformat(), claim.id)
    r = Reading(s.id, period, "range", observations=list(obs))
    if obs:
        values = [o.value for o in obs]
        r.low, r.high = min(values), max(values)
        r.official_value = r.low if r.low == r.high else None
    else:
        r.note = f"no observations in {period}"
    return r


def _decide(res: ClaimResult, run: Run) -> None:
    claim = res.claim
    stated, hedged = claim.stated_value, claim.hedged
    direction = 0
    if any(r.kind == "change" for r in res.readings):
        from .lexicon import hints
        direction = hints(claim.source_text).direction
        if direction == 0:
            res.add_label("direction_unknown")
            res.notes.append("Direction of the change not read from the text; only its size is compared.")
    for r in res.readings:
        if r.kind == "range" and r.low is not None:
            r.matched = compare_range(stated, r.low, r.high, hedged)
        elif r.kind == "change" and r.official_value is not None:
            # "en nedgang på 0,3 prosentpoeng" is -0.3 (B31).
            signed = abs(stated) * direction if direction else stated.copy_abs()
            official = r.official_value if direction else r.official_value.copy_abs()
            r.matched = compare_point(signed, official, hedged)
        elif r.official_value is not None:
            r.matched = compare_point(stated, r.official_value, hedged)

    with_data = [r for r in res.readings if r.has_data]
    if any(r.matched for r in res.readings):
        res.verdict = MATCHED
    elif not with_data:
        res.verdict = CANNOT_VERIFY
        res.add_label("no_data")
    elif len(with_data) < len(res.readings):
        res.verdict = CANNOT_VERIFY
        res.add_label("incomplete_data")
    else:
        res.verdict = MISMATCHED

    for r in res.readings:
        if r.note:
            res.notes.append(r.note)

    # D4: with several readings, show each figure and what it measures.
    if len(res.readings) > 1:
        for r in res.readings:
            concept = run.series[r.series_id].concept
            if r.kind == "range" and r.low is not None:
                shown = f"{r.low} to {r.high}"
            else:
                shown = str(r.official_value) if r.official_value is not None else "no data"
            fit = "matches" if r.matched else "does not match"
            res.notes.append(f"{concept}, {r.period}: {shown} ({fit}).")


# ------------------------------------------------------------------ provenance


def check_provenance(results: list[ClaimResult], run: Run) -> None:
    """Every official number must trace back to observations fetched in this run."""
    for res in results:
        for r in res.readings:
            if not r.has_data:
                continue
            if not r.observations:
                raise ProvenanceError(f"{res.claim.id}: {r.series_id} has a value but no observations")
            for o in r.observations:
                if not run.is_registered(o):
                    raise ProvenanceError(f"{res.claim.id}: observation for {r.series_id} "
                                          f"{o.period} was not fetched in this run")
            vals = [o.value for o in r.observations]
            if r.kind == "point":
                ok = r.official_value == vals[-1]
            elif r.kind == "change":
                ok = r.official_value == vals[-1] - vals[0]
            else:
                ok = (r.low, r.high) == (min(vals), max(vals))
            if not ok:
                raise ProvenanceError(f"{res.claim.id}: official value for {r.series_id} "
                                      "does not equal the fetched observations")
