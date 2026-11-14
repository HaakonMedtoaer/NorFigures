# Mapper agent: contract

Status: draft. Implemented in weekend 3.

## Input
- One claim from the extractor.
- `facts/ledger.md`.
- MCP tools `search_series` and `describe_series` (read-only).

## Output
Either `mapping: {source, series_id, query}`, where `series_id` is a ledger key
(for example `kpi_12m`) and `query` holds the period to fetch, or
`unmapped` with a reason.

## Must
- Prefer the canonical series the ledger lists for the concept.
- When a claim has two valid readings (KPI vs KPI-JAE, monthly vs 12-month),
  return both mappings and add the label `ambiguous_measure`.

## Must not
- Call `fetch_values`, or state, estimate or remember any value.
- Choose a series the ledger does not list as canonical without flagging it.
- Pick silently between two valid measures.
