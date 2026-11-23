"""Read-only MCP server over the official sources (SSB, Norges Bank, NAV).

Run:  python -m norfigures.mcp_server     (stdio; needs `pip install 'norfigures[agents]'`)

Every tool goes through the same fetch code as the verifier, so the host
allowlist and GET-only rule apply. No tool writes anything.
"""

from __future__ import annotations


from .fetch import fetch_series
from .ledger import load
from .net import Client
from .sources import norges_bank, ssb

SOURCES = ("ssb", "norges_bank", "nav")


def _client() -> Client:
    return Client.from_env()


def search_series(source: str, text: str) -> list[dict]:
    """Find candidate tables (SSB) or ledger series (Norges Bank, NAV) by keyword."""
    if source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}")
    if source == "ssb":
        return ssb.search_tables(_client(), text)
    words = text.lower().split()
    return [{"series_id": s.id, "flow": s.flow, "key": s.key, "table": s.table, "concept": s.concept}
            for s in load().values()
            if s.source == source and any(w in (s.concept + " " + s.id).lower() for w in words)]


def describe_series(source: str, series_id: str) -> dict:
    """Dimensions, units, frequency and latest period for a ledger series or table."""
    if source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}")
    series = load()
    s = series.get(series_id)
    if s is not None and s.source != source:
        raise ValueError(f"{series_id} belongs to {s.source}, not {source}")
    if source == "ssb":
        info = ssb.describe_table(_client(), s.table if s else series_id)
        info["dimensions"] = {k: {"label": v["label"], "codes": dict(list(v["codes"].items())[:50]),
                                  "count": len(v["codes"])} for k, v in info["dimensions"].items()}
    elif source == "nav":
        # NAV has no API to describe; the ledger says what is read (D20).
        if s is None:
            raise ValueError("NAV series must be a ledger ID (nav_registered)")
        info = {"table": s.table, "sheet": s.selection["sheet"], "row": s.selection["row"],
                "breaks": [list(b) for b in s.breaks]}
    else:
        if s is None:
            flow, _, key = series_id.partition("/")
            if not key:
                raise ValueError("Norges Bank series must be a ledger ID or FLOW/KEY")
        else:
            flow, key = s.flow, s.key
        info = norges_bank.describe_series(_client(), flow, key)
    if s is not None:
        info["ledger"] = {"series_id": s.id, "concept": s.concept, "unit": s.unit,
                          "measure": s.measure, "frequency": s.frequency, "confirmed": s.confirmed}
    return info


def fetch_values(series_id: str, start: str, end: str) -> dict:
    """Official observations for a ledger series between start and end (inclusive)."""
    s = load().get(series_id)
    if s is None:
        raise ValueError(f"unknown series {series_id!r}; use a ledger series ID")
    obs = fetch_series(_client(), s, start=start, end=end)
    return {"series_id": s.id, "concept": s.concept, "unit": s.unit,
            "url": obs[0].url if obs else None,
            "retrieved_at": obs[0].retrieved_at if obs else None,
            "observations": [{"period": o.period, "value": str(o.value)} for o in obs]}


def build_server():
    from mcp.server.mcpserver import MCPServer
    from mcp.types import ToolAnnotations

    ro = ToolAnnotations(read_only_hint=True, destructive_hint=False,
                         idempotent_hint=True, open_world_hint=True)
    server = MCPServer(
        name="norfigures",
        instructions="Read-only access to official Norwegian figures from SSB, Norges Bank and NAV. "
                     "Values are returned as strings with the source's own precision.")
    server.tool(annotations=ro)(search_series)
    server.tool(annotations=ro)(describe_series)
    server.tool(annotations=ro)(fetch_values)
    return server


if __name__ == "__main__":
    build_server().run("stdio")
