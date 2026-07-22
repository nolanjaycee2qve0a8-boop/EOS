# TASK-005 — Deterministic Runtime Kernel Tick

## Status

IN REVIEW

## Objective

Establish the first EOS Runtime Kernel boundary for executing exactly one
explicit deterministic system tick.

## Scope

- An immutable TickResult carrying the exact DecisionResult and progressed
  EventJournal.
- An immutable RuntimeKernel coordinating one DecisionPipeline execution.
- Deterministic EventRecord sequence derivation from existing journal state.
- Focused validation, public imports, and unit tests.

## Non-goals

- While loops, schedulers, timers, threads, async execution, or a 100 ms loop.
- Device communication through Modbus, CAN, MQTT, or other protocols.
- Databases, filesystem persistence, cloud communication, or serialization.
- EMS algorithms, optimization, forecasting, or production policies.
- State machines, fault recovery, command execution, or event publication.
- Generated Events, Commands, IDs, timestamps, or random sequences.

## Architecture

RuntimeKernel receives an existing DecisionPipeline and EventJournal. Its tick
method validates one Snapshot and Mission, executes the pipeline once, and
appends the returned DecisionResult Events to a new journal value. TickResult
returns the exact DecisionResult and the progressed journal.

The kernel owns one-tick decision orchestration and journal progression. It
does not own time, scheduling, devices, storage, or repeated execution.

## Tick Lifecycle

1. Validate the Snapshot and Mission.
2. Execute DecisionPipeline exactly once with those same objects.
3. Receive the exact DecisionResult.
4. Derive the next sequence from the last existing EventRecord, or zero when
   the journal is empty.
5. Wrap each existing result Event in an EventRecord in result order.
6. Append each record through the immutable EventJournal boundary.
7. Return TickResult with the exact DecisionResult and progressed journal.

## Acceptance Criteria

- RuntimeKernel and TickResult are frozen slotted dataclasses.
- Invalid runtime object types raise TypeError with field names.
- Pipeline execution occurs exactly once per tick.
- Snapshot, Mission, DecisionResult, and Event identities are preserved.
- Event order and deterministic sequence progression are preserved.
- The original EventJournal and all domain inputs remain unchanged.
- All existing tests and repository quality checks pass.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
pre-commit run --all-files
~~~
