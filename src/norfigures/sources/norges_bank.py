"""Norges Bank open data, SDMX REST (https://data.norges-bank.no/api).

No API key. Series are addressed as {flow}/{key}, e.g. EXR/B.EUR.NOK.SP.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from ..net import Client
from .base import Observation, SourceError

BASE = "https://data.norges-bank.no/api"
SOURCE = "norges_bank"


def describe_series(client: Client, flow: str, key: str) -> dict:
    """Latest observation plus series attributes, as a cheap 'describe'."""
    resp = client.get(f"{BASE}/data/{flow}/{key}",
                      {"format": "sdmx-json", "lastNObservations": "1", "locale": "en"})
    d = resp.json()
    try:
        st = d["data"]["structure"]
        dims = {dim["id"]: [v.get("name", v["id"]) for v in dim["values"]]
                for dim in st["dimensions"]["series"]}
    except (KeyError, TypeError) as e:
        raise SourceError(f"unexpected SDMX-JSON shape from {resp.url}: {e}") from e
    obs = parse_sdmx(d, f"{flow}/{key}", resp.url, resp.retrieved_at)
    return {"flow": flow, "key": key, "name": st.get("name"), "dimensions": dims,
            "latest_period": obs[-1].period if obs else None}


def fetch(client: Client, series_id: str, flow: str, key: str,
          start: str | None = None, end: str | None = None,
          last_n: int | None = None) -> list[Observation]:
    """Fetch one series. Periods are YYYY-MM-DD. Give start/end or last_n."""
    params = {"format": "sdmx-json", "locale": "en"}
    if start or end:
        if start:
            params["startPeriod"] = start
        if end:
            params["endPeriod"] = end
    else:
        params["lastNObservations"] = str(last_n or 1)
    resp = client.get(f"{BASE}/data/{flow}/{key}", params)
    return parse_sdmx(resp.json(), series_id, resp.url, resp.retrieved_at)


def parse_sdmx(d: dict, series_id: str, url: str, retrieved_at: str) -> list[Observation]:
    """Flatten an SDMX-JSON 1.0 data message holding a single series."""
    try:
        datasets = d["data"]["dataSets"]
        st = d["data"]["structure"]
        times = [v["id"] for v in st["dimensions"]["observation"][0]["values"]]
        series_dims = st["dimensions"]["series"]
    except (KeyError, TypeError, IndexError) as e:
        raise SourceError(f"unexpected SDMX-JSON shape from {url}: {e}") from e
    if not datasets or not datasets[0].get("series"):
        return []
    series = datasets[0]["series"]
    if len(series) != 1:
        raise SourceError(f"expected one series from {url}, got {len(series)}")
    (series_key, body), = series.items()
    try:
        dims = {dim["id"]: dim["values"][int(i)]["id"]
                for dim, i in zip(series_dims, series_key.split(":"))}
        observations = sorted(body.get("observations", {}).items(), key=lambda kv: int(kv[0]))
        periods = [times[int(idx)] for idx, _ in observations]
    except (KeyError, TypeError, IndexError, ValueError, AttributeError) as e:
        raise SourceError(f"unexpected SDMX-JSON shape from {url}: {e!r}") from e

    out = []
    for period, (_, obs) in zip(periods, observations):
        raw = obs[0] if obs else None
        if raw in (None, ""):
            continue
        try:
            value = Decimal(str(raw))
        except InvalidOperation as e:
            raise SourceError(f"non-numeric value {raw!r} from {url}") from e
        out.append(Observation(SOURCE, series_id, period, value, url,
                               retrieved_at, dict(dims)))
    return out
