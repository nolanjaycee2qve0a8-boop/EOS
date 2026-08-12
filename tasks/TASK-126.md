# TASK-126 - Explainable MPC Decision CSV Export

## Objective

Provide a deterministic, in-memory CSV representation of one or more exact
`ExplainableMPCDecisionJournalRecord` values for analytics, diagnostics, and
future export tooling.

## Schema

`EXPLAINABLE_MPC_DECISION_CSV_COLUMNS` is the explicit, stable 24-column CSV
schema. `ExplainableMPCDecisionCSVRow` contains only primitives: strings,
floats, and booleans. It retains raw domain numeric values and machine tokens,
while carrying the journal record's existing formatted explanation text exactly.

## Boundaries

The mapper consumes one exact journal record and uses the existing timestamp,
strategy descriptor, candidate/final actions, evidence strings, booleans, raw
numbers, and formatted text. The serializer consumes caller-ordered row tuples
and emits header-inclusive text through the Python standard-library `csv`
module with deterministic `\n` terminators and proper comma/quote/newline
escaping.

```text
MPC Cycle
    -> Explanation
    -> Formatted Explanation
    -> Journal Record
    -> CSV Row
    -> CSV text
    -> future file exporter / replay tooling
```

## Responsibility separation

CSV serialization is presentation only. It is not persistence, optimization,
explanation generation, EventJournal integration, or execution. No filesystem
path or write operation is part of TASK-126.
