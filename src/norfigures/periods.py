"""Period helpers: parsing, month arithmetic, inference from a publication date."""

from __future__ import annotations

from datetime import date, timedelta

# KPI for month M is released by SSB around the 10th of month M+1 (ledger).
# Up to this day of the month we cannot tell whether last month's figure was
# already out, so both candidate months are checked (D14 with D4/D5).
KPI_RELEASE_UNCERTAIN_UNTIL_DAY = 15


def kind(period: str) -> str:
    return {4: "year", 7: "month", 10: "day"}[len(period)]


def parse_day(period: str) -> date:
    return date.fromisoformat(period)


def month_of(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def add_months(month: str, n: int) -> str:
    y, m = int(month[:4]), int(month[5:7])
    idx = y * 12 + (m - 1) + n
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def month_bounds(month: str) -> tuple[date, date]:
    first = date(int(month[:4]), int(month[5:7]), 1)
    nxt = date.fromisoformat(add_months(month, 1) + "-01")
    return first, nxt - timedelta(days=1)


def period_start(period: str) -> date:
    k = kind(period)
    if k == "day":
        return parse_day(period)
    if k == "month":
        return month_bounds(period)[0]
    return date(int(period), 1, 1)


def infer_monthly(published: date) -> list[str]:
    """Candidate months for a monthly figure quoted without a period (D14)."""
    last = add_months(month_of(published), -1)
    if published.day <= KPI_RELEASE_UNCERTAIN_UNTIL_DAY:
        return [last, add_months(last, -1)]
    return [last]
