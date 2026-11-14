# Extractor agent: contract

Status: draft. Implemented in weekend 3.

## Input
- Raw text (Norwegian or English).
- Publication date (`--published`), if given.

## Output
A JSON list of claims, each valid against the claim schema (spec section 6),
with these fields set: `id`, `source_text`, `indicator`, `measure`, `period`,
`period_inferred`, `unit`, `stated_value`, `status`, `labels`.

`status` is one of `checkable`, `forecast`, `no_figure`, `ambiguous`, `out_of_scope`.

## Must
- Report every numeric claim about an economic figure, including ones it
  cannot classify (as `ambiguous` or `out_of_scope`, with a reason).
- Copy `source_text` verbatim from the input.
- Copy `stated_value` exactly as written, converting only the decimal comma
  ("3,1" becomes 3.1). Keep trailing zeros meaningful: "4,0" has one decimal.
- Mark forecasts (future tense, "venter", "anslår", "expects", future period)
  as `forecast`.

## Must not
- Rewrite or correct numbers.
- Skip a numeric claim without reporting it.
- Guess a missing period. Leave it null and add label `period_missing`; code
  infers it from `--published` under the rule in spec section 7.
- Supply any official value.

Output that fails schema validation is a failed extraction (exit 3). It is
never repaired silently.
