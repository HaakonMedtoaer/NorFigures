# Mapper agent: contract

Status: draft. Implemented in weekend 3.

## Input
- One claim from the extractor.
- `facts/ledger.md`.
- MCP tools `search_series` and `describe_series` (read-only).

## Output
`mappings`: a list of `{series_id}` entries, where `series_id` is a ledger key
(for example `kpi_12m`). The first entry is the canonical reading. An empty
list means unmapped; give the reason in `notes`. The period stays on the claim;
code builds the query (decision B8).

## Must
- Prefer the canonical series the ledger lists for the concept.
- When a claim has two valid readings (KPI vs KPI-JAE, monthly vs 12-month),
  return both mappings, canonical first (D4). Code adds `ambiguous_measure`.

## Must not
- Call `fetch_values`, or state, estimate or remember any value.
- Choose a series the ledger does not list as canonical without flagging it.
- Pick silently between two valid measures.
