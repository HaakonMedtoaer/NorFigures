"""SSB Statbank, PxWebApi v2 (https://data.ssb.no/api/pxwebapi/v2).

No API key. Rate limit observed 2026-11-14: 40 requests per 60 s
(header x-ratelimit-policy: 40;w=60s).
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from itertools import product

from ..net import Client, FetchError
from .base import Observation, SourceError

BASE = "https://data.ssb.no/api/pxwebapi/v2"
SOURCE = "ssb"

_MONTH = re.compile(r"^(\d{4})M(\d{2})$")


def to_ssb_month(period: str) -> str:
    """'2026-10' -> '2026M10'."""
    m = re.fullmatch(r"(\d{4})-(\d{2})", period)
    if not m:
        raise ValueError(f"expected YYYY-MM, got {period!r}")
    return f"{m.group(1)}M{m.group(2)}"


def from_ssb_period(code: str) -> str:
    """'2026M10' -> '2026-10'. Other codes pass through unchanged."""
    m = _MONTH.match(code)
    return f"{m.group(1)}-{m.group(2)}" if m else code


def search_tables(client: Client, text: str, page_size: int = 20) -> list[dict]:
    resp = client.get(f"{BASE}/tables",
                      {"query": text, "lang": "en", "pageSize": str(page_size)})
    return [{"id": t["id"], "label": t["label"], "last_period": t.get("lastPeriod")}
            for t in resp.json().get("tables", [])]


def describe_table(client: Client, table_id: str) -> dict:
    resp = client.get(f"{BASE}/tables/{table_id}/metadata",
                      {"lang": "en", "outputFormat": "json-stat2"})
    d = resp.json()
    dims = {}
    for dim_id in d["id"]:
        cat = d["dimension"][dim_id]["category"]
        codes = sorted(cat["index"], key=cat["index"].get)
        dims[dim_id] = {"label": d["dimension"][dim_id]["label"],
                        "codes": {c: cat["label"].get(c, c) for c in codes}}
    time_codes = list(dims.get("Tid", {}).get("codes", {}))
    return {"table_id": table_id, "label": d.get("label"), "updated": d.get("updated"),
            "dimensions": dims, "latest_period": time_codes[-1] if time_codes else None}


def fetch(client: Client, series_id: str, table: str, selection: dict[str, str],
          start: str | None = None, end: str | None = None,
          last_n: int | None = None) -> list[Observation]:
    """Fetch one series. `selection` fixes every non-time dimension to one code.

    Periods are YYYY-MM for monthly tables and YYYY for annual ones. Give either
    start/end or last_n (default: last 1).
    """
    params = {"lang": "en", "outputFormat": "json-stat2"}
    for dim, code in selection.items():
        params[f"valueCodes[{dim}]"] = code
    if start or end:
        lo, hi = start or end, end or start
        if re.fullmatch(r"\d{4}", lo) and re.fullmatch(r"\d{4}", hi):
            if lo > hi:
                raise ValueError(f"start {lo} is after end {hi}")
            params["valueCodes[Tid]"] = ",".join(str(y) for y in range(int(lo), int(hi) + 1))
        else:
            params["valueCodes[Tid]"] = _range(to_ssb_month(lo), to_ssb_month(hi))
    else:
        params["valueCodes[Tid]"] = f"top({last_n or 1})"
    try:
        resp = client.get(f"{BASE}/tables/{table}/data", params)
    except FetchError as e:
        if not (start or end):
            raise
        lo, hi = start or end, end or start
        newest = _newest_if_not_published(e, client, series_id, table, selection, hi)
        if newest is None:
            raise
        if newest < lo:
            return []
        # Only the end of the range is not out yet ("from September to October" before
        # October's release): return what is published, and the caller sees the gap.
        return fetch(client, series_id, table, selection, start=lo, end=newest)
    try:
        # Numbers straight from the source's text into Decimal, never through float.
        data = json.loads(resp.body, parse_float=Decimal)
    except json.JSONDecodeError as e:
        raise SourceError(f"answer from {resp.url} is not JSON: {e}") from e
    return parse_jsonstat(data, series_id, resp.url, resp.retrieved_at)


def _newest_if_not_published(err: FetchError, client: Client, series_id: str, table: str,
                             selection: dict[str, str], end: str) -> str | None:
    """SSB answers 400 "Non-existent value" for a period the table does not hold yet,
    and also for a wrong selection code. Only the first is "no value yet": the same
    selection must answer, with a newest period before the end of the range asked
    for (D21, B48). Returns that newest period, or None if the error stands."""
    if err.status != 400 or "Non-existent value" not in err.body:
        return None
    latest = fetch(client, series_id, table, selection, last_n=1)  # raises if the selection is wrong
    if latest and latest[-1].period < end:
        return latest[-1].period
    return None


def _range(lo: str, hi: str) -> str:
    """List every month code from lo to hi inclusive (PxWebApi accepts a list)."""
    ly, lm = int(lo[:4]), int(lo[5:])
    hy, hm = int(hi[:4]), int(hi[5:])
    if (ly, lm) > (hy, hm):
        raise ValueError(f"start {lo} is after end {hi}")
    codes = []
    y, m = ly, lm
    while (y, m) <= (hy, hm):
        codes.append(f"{y}M{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return ",".join(codes)


def parse_jsonstat(d: dict, series_id: str, url: str, retrieved_at: str) -> list[Observation]:
    """Flatten a json-stat2 dataset into observations, skipping missing values."""
    try:
        ids, sizes, values = d["id"], d["size"], d["value"]
        cats = []
        for dim_id in ids:
            index = d["dimension"][dim_id]["category"]["index"]
            cats.append(sorted(index, key=index.get))
    except (KeyError, TypeError) as e:
        raise SourceError(f"unexpected json-stat2 shape from {url}: {e}") from e
    if [len(c) for c in cats] != sizes:
        raise SourceError(f"json-stat2 size mismatch from {url}")
    total = 1
    for n in sizes:
        total *= n
    if isinstance(values, list) and len(values) != total:
        raise SourceError(f"json-stat2 from {url} has {len(values)} values for {total} cells")
    if not isinstance(values, (list, dict)):
        raise SourceError(f"json-stat2 from {url} has no value list")
    statuses = d.get("status") or {}
    time_dim = (d.get("role", {}).get("time") or ["Tid"])[0]
    metric_dim = (d.get("role", {}).get("metric") or ["ContentsCode"])[0]
    units = d["dimension"].get(metric_dim, {}).get("category", {}).get("unit", {})

    out = []
    for flat, combo in enumerate(product(*cats)):
        raw = values[flat] if isinstance(values, list) else values.get(str(flat))
        if raw is None:
            continue
        try:
            value = Decimal(str(raw))
        except InvalidOperation as e:
            raise SourceError(f"non-numeric value {raw!r} from {url}") from e
        dims = dict(zip(ids, combo))
        dims["_table"] = url.split("/tables/")[1].split("/")[0] if "/tables/" in url else None
        # JSON numbers drop trailing zeros (3.0 arrives as 3). Restore the
        # published precision, which the rounding rule depends on.
        decimals = units.get(dims.get(metric_dim), {}).get("decimals")
        if decimals is not None:
            shown = value.quantize(Decimal(1).scaleb(-int(decimals)))
            if shown != value:
                # As for NAV: never round a source's figure ourselves; the rounding
                # rule (D8) needs the precision the source published.
                raise SourceError(f"value {raw} from {url} has more decimals than the "
                                  f"{decimals} SSB declares; refusing to round it")
            value = shown
        if str(flat) in statuses:
            dims["_status"] = statuses[str(flat)]
        period = from_ssb_period(dims.pop(time_dim))
        out.append(Observation(SOURCE, series_id, period, value, url, retrieved_at, dims))
    return out
