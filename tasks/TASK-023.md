# TASK-023 — Deterministic Replay Boundary

## Status

IN REVIEW

## Objective

Add a stateless deterministic replay boundary for immutable
RuntimeExecutionTrace observations.

Replay is not re-execution. Replay means:

> Deterministic observation of an already completed lifecycle.

## Architecture

~~~text
RuntimeExecutionTrace
        |
        v
RuntimeReplay
        |
        v
ReplayResult
~~~

RuntimeReplay reads the trace's exact source, dispatched, and progressed ticks
and returns an immutable ReplayResult containing those same objects.

## Identity and Determinism

Given the same trace, every replay result retains:

- `result.source_tick is trace.source_tick`;
- `result.dispatched_tick is trace.dispatched_tick`; and
- `result.progressed_tick is trace.progressed_tick`.

No tick, result, journal, command, event, or EventRecord is copied. Repeated
replay produces the same lifecycle observation without mutating the trace.

## Observation Only

Replay does not call policies, runtime ticks, progression, dispatchers, or
CommandExecutor. It does not append records, create journals, generate events,
or perform lifecycle recovery.

ReplayResult validates the dispatch-to-source identity and the source
EventRecord identity prefix in the progressed journal. This defensively rejects
a RuntimeExecutionTrace that was fabricated outside its normal validated
construction path.

## Statelessness

RuntimeReplay has empty slots and stores no trace, result, cache, history,
timestamp, UUID, telemetry, or global runtime state.

## Non-goals

- Runtime recovery or policy re-evaluation.
- Device execution replay, command retry, rollback, or compensation.
- Persistence, database storage, cloud replay services, or telemetry.
- Journal mutation or creation of lifecycle events.

## Validation

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
pre-commit run --all-files
~~~
