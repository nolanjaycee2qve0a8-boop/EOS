# TASK-125 - Explainable MPC Decision Journal Record

## Objective

Create a stable immutable per-decision read-model record from one exact
physical MPC cycle, its TASK-123 machine explanation, and its TASK-124 human
presentation.

## Provenance

```text
PhysicallyAwareMPCCycleResult
    -> MPCDecisionExplanation
    -> FormattedMPCDecisionExplanation
    -> ExplainableMPCDecisionJournalRecord
```

The input validates that the explanation references the exact cycle and the
formatted explanation references the exact machine explanation. The record then
retains its exact input, strategy descriptor, candidate/final `DecisionIntent`
objects, exact reason and violation tuples, raw numeric evidence, and existing
formatted text.

## Semantics

Timestamp is the exact decision-context timestamp, never a write-time clock.
All raw values come directly from the existing explanation read model; the
builder does not traverse the optimization graph, re-run a formatter, or derive
new feasibility values. Machine-readable evidence and formatted text coexist
so later CSV/API/UI consumers can choose their own presentation.

## Responsibility separation

The record is historical/read-model data only. It is not persistence, a kernel
`EventJournal` entry, execution, optimizer work, constraint evaluation, or
explanation inference. Any future Event, CSV, JSON, replay, or UI adaptation is
an explicit later boundary.

## Non-goals

No `EventJournal` or `EventRecord` modification; no Event adapter, append,
filesystem/database/network I/O, logging backend, cache, optimizer, projector,
evaluator, MPC rerun, Simulator, Actuation, Runtime, Device, or Command work.
