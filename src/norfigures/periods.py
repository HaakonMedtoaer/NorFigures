"""Period helpers: parsing, month arithmetic, inference from a publication date."""

from __future__ import annotations

from datetime import date, timedelta

# Default release window for a monthly series: KPI for month M is released by SSB
# around the 10th of month M+1 (ledger). Up to the 15th we cannot tell whether last
# month's figure was already out, so both candidate months are checked (D14, B11).
DEFAULT_RELEASE_WINDOW = (1, 15)


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


def bounds(period: str) -> tuple[date, date]:
    """First and last day of a day, month or year period."""
    k = kind(period)
    if k == "day":
        d = parse_day(period)
        return d, d
    if k == "month":
        return month_bounds(period)
    return date(int(period), 1, 1), date(int(period), 12, 31)


def period_start(period: str) -> date:
    k = kind(period)
    if k == "day":
        return parse_day(period)
    if k == "month":
        return month_bounds(period)[0]
    return date(int(period), 1, 1)


def infer_monthly(published: date, window: tuple[int, int] | None = None,
                  offset: int = 1) -> list[str]:
    """Candidate months for a monthly figure quoted without a period (D14).

    `window` is (first_day, last_day) of month M+offset in which month M is
    published (ledger `release_window`, `release_month_offset`). With offset 1
    (SSB), before the window the latest published month is M-2; inside it, either
    could be meant, so both are checked; after it, M-1 (B42). NAV publishes in
    the month itself (offset 0, D20).
    """
    first, last_day = window or DEFAULT_RELEASE_WINDOW
    last = add_months(month_of(published), -offset)
    if published.day < first:
        return [add_months(last, -1)]
    if published.day <= last_day:
        return [last, add_months(last, -1)]
    return [last]
