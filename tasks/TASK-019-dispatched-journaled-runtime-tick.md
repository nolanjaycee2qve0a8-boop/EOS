# TASK-019 — Dispatched Journaled EMS Runtime Tick

## Status

IN REVIEW

## Objective

Add an explicit second runtime phase that dispatches commands from one
already-completed JournaledEMSTick. The caller owns the completed immutable tick
before any external command side effect begins.

## Scope

- Add immutable DispatchedJournaledEMSTick containing the exact source tick.
- Add `JournaledEMSRuntime.dispatch(tick, dispatcher)`.
- Validate both inputs before accessing nested tick data or command delegation.
- Delegate exclusively through CommandExecutor exactly once.
- Construct the dispatched result only after successful execution.
- Preserve source tick, execution, cycle, result, journal, and command identities.

## Two-phase Contract

Policy execution and event journaling complete through
`JournaledEMSRuntime.tick` before dispatch begins. The caller then explicitly
passes that completed JournaledEMSTick to `JournaledEMSRuntime.dispatch`.

Dispatch validates JournaledEMSTick and CommandDispatcher, then calls:

`CommandExecutor.execute(dispatcher, tick.execution.cycle.result)`

exactly once. Only after normal completion does it return
DispatchedJournaledEMSTick containing the exact source tick.

## Empty and Failure Behavior

Empty command results still delegate once to CommandExecutor, which owns the
no-op behavior.

Executor and dispatcher exceptions propagate unchanged. No dispatched result is
created, no command is retried, later commands remain undispatched, earlier
commands are not rolled back, and the source tick and journal remain unchanged.

## Ownership

The dispatched result contains exactly one tick field. It stores no duplicate
execution, cycle, result, journal, command, or dispatcher. Runtime dispatch
does not execute policies, create cycles, journal events, append records, or
iterate commands directly.

## Non-goals

- Combined tick-and-dispatch or progress-and-dispatch operations.
- Concrete adapters, routing, multiple dispatchers, or asset routing.
- Retries, timeouts, rollback, compensation, receipts, or execution status.
- Command or failure events, command journaling, loops, schedulers, or queues.
- Threads, async execution, persistence, telemetry, clocks, or UUID generation.
- Device feedback, PCS control, or SOC updates.

## Acceptance Criteria

- Dispatch delegates once through CommandExecutor with exact dependencies.
- The returned immutable result retains the exact source tick.
- Empty, event-only, successful, and failed executions preserve contracts.
- Policy and tick execution are not repeated during dispatch.
- Invalid inputs fail before command delegation.
- Legacy runtime exports and behavior remain available.
- All repository quality checks pass.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
pre-commit run --all-files
~~~
