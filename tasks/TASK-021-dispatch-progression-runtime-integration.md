# TASK-021 — Dispatch Progression Runtime Integration

## Status

IN REVIEW

## Objective

Add one stateless integration boundary that composes the existing deterministic
runtime lifecycle:

`tick → journaled result → command dispatch → progression`

The integration reuses existing runtime contracts and introduces no duplicate
decision, journaling, command, or progression behavior.

## Contract

`DispatchProgressionRuntime.execute` accepts explicit dependencies for the
current tick and the next progression:

- current EMSPolicy, EnergySystemContext, and EventJournal;
- CommandDispatcher;
- next EMSPolicy and EnergySystemContext.

All six inputs are validated before any lifecycle stage. The integration then:

1. calls `JournaledEMSRuntime.tick` exactly once;
2. passes its exact result to `JournaledEMSRuntime.dispatch` exactly once;
3. passes the exact dispatched result to
   `JournaledEMSRuntime.progress_after_dispatch` exactly once; and
4. returns the exact progressed JournaledEMSTick.

## Identity and Failure

The integration does not copy or rebuild contexts, ticks, decision results,
journals, records, commands, or progression results.

A decision failure prevents dispatch. A dispatcher failure prevents
progression. Exceptions propagate unchanged, and no stage is retried.

## Statelessness

DispatchProgressionRuntime has empty slots and retains no policy, context,
journal, dispatcher, tick, dispatched result, progression, history, or runtime
cache.

## Non-goals

- Changes to existing tick, progression, dispatch, or dispatch-progression
  contracts.
- Device adapters or Modbus, CAN, MQTT, HTTP, serial, or PCS protocols.
- Retries, timeouts, rollback, compensation, queues, threads, or async work.
- Persistence, runtime state caches, telemetry, clocks, timestamps, or UUIDs.
- Exactly-once external effect guarantees.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
pre-commit run --all-files
~~~
