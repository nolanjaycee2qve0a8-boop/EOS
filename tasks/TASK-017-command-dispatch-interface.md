# TASK-017 — Command Dispatch Interface Boundary

## Status

IN REVIEW

## Objective

Define the abstract boundary through which immutable domain Command objects may
later be submitted to external infrastructure adapters. This task introduces
only the interface contract and no production implementation.

## Scope

- Add the abstract, slotted CommandDispatcher boundary.
- Accept exactly one Command per `dispatch` call.
- Return None after normal completion.
- Propagate implementation exceptions unchanged.
- Expose only CommandDispatcher from `kernel.dispatch`.
- Verify exact Command identity with test-only implementations.

## Interface Contract

`CommandDispatcher.dispatch(command)` receives the exact immutable Command
supplied by its caller. Implementations complete normally by returning None and
signal failures by raising exceptions.

The boundary does not copy, normalize, rebuild, mutate, execute, persist, or
journal commands. It defines no retry, timeout, batching, ordering,
partial-failure, or receipt semantics.

## Ownership

CommandDispatcher owns no EMS policy, DecisionResult, runtime tick, journal,
queue, scheduler, connection, or device. Protocol conversion and physical
command execution belong to future external adapters.

## Non-goals

- Concrete production dispatchers or device-specific adapters.
- Modbus, CAN, MQTT, HTTP, serial, PCS, or register semantics.
- Automatic or batch dispatch of DecisionResult commands.
- Receipts, execution results, status enums, retries, or timeouts.
- Loops, schedulers, queues, threads, async execution, or clocks.
- Persistence, command journaling, telemetry, or device control.
- SOC updates, EMS algorithms, optimization, or forecasting.

## Acceptance Criteria

- CommandDispatcher is abstract, slotted, and cannot be instantiated directly.
- A test-only minimal subclass receives exact Command identities.
- Normal completion returns None and exceptions propagate unchanged.
- The public package exports only CommandDispatcher.
- No concrete production dispatcher is introduced.
- All repository quality checks pass.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
pre-commit run --all-files
~~~
