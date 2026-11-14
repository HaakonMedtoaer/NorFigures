# Explainer agent: contract (optional)

Status: draft. Optional; after the core loop works.

## Input
One finished claim record, verdict already set by code.

## Output
One or two plain sentences per verdict, in the language of the claim.

## Must not
- Change a verdict.
- Introduce any number absent from the record.

A code check rejects any explanation containing a number not present in the record.
