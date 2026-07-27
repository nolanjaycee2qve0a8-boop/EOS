# TASK-022 — Deterministic Runtime Execution Trace Boundary

## Status

IN REVIEW

## Objective

Add an immutable observation boundary that preserves the critical identity
relationships from one already-completed EMS runtime lifecycle:

`decision → journal → dispatch → progression`

## Trace Contract

RuntimeExecutionTrace contains exactly:

- the source JournaledEMSTick;
- the DispatchedJournaledEMSTick that retains that exact source tick; and
- the progressed JournaledEMSTick.

Construction accepts only completed lifecycle objects. It validates the exact
dispatch-to-source relationship and requires the progressed journal to retain
every source EventRecord as the same object in its deterministic prefix.

The trace never executes a policy, rebuilds a context, dispatches a command, or
progresses a tick.

## Why Execution Trace Is Needed

The runtime lifecycle deliberately spans separate deterministic and
side-effecting boundaries. A trace gives tests, diagnostics, and higher-level
callers one immutable object through which they can inspect the exact objects
that participated without weakening those ownership boundaries.

## Why Trace Is Not Runtime State

The trace is a completed observation value. It does not influence future
execution, allocate sequence numbers, select policies, retain a dispatcher, or
cache lifecycle progress. Separate lifecycles create separate trace objects and
share no trace-owned mutable state.

## Why Trace Does Not Persist

Persistence requires storage ownership, serialization, schema evolution,
failure handling, and retention policy. Those responsibilities are external to
an immutable kernel observation boundary. RuntimeExecutionTrace therefore
stores no database reference and performs no I/O.

## Non-goals

- Runtime caches, global storage, databases, or persistence.
- Timestamp, UUID, telemetry, or logging generation.
- Policy evaluation, context reconstruction, command dispatch, or progression.
- Copying ticks, results, journals, commands, events, or EventRecords.
- Changes to existing runtime lifecycle boundaries.

## Validation

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
pre-commit run --all-files
~~~
