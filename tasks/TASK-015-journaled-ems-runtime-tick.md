# TASK-015 — Journaled EMS Runtime Tick

## Status

IN REVIEW

## Objective

Introduce one stateless runtime entry point for a single journaled EMS
execution. The boundary validates explicit inputs, delegates to the existing
JournaledEMSExecutionService exactly once, and returns the exact resulting
JournaledEMSCycle inside an immutable JournaledEMSTick.

## Scope

- An immutable, slotted JournaledEMSTick with exactly one execution field.
- A stateless JournaledEMSRuntime with one explicit `tick` operation.
- Complete input validation before service delegation.
- Exact identity and downstream exception preservation.
- Stable public imports and focused unit tests.

## Non-goals

- Runtime loops, scheduling, timers, threads, async execution, sleep, or retries.
- Clocks, timestamps, UUID generation, persistence, communication, or telemetry.
- Commands, devices, PCS, batteries, or SOC control.
- EMS algorithms, optimization, forecasting, policy registration, or selection.
- Direct policy, executor, cycle, journal, event-record, or append operations.
- Changes to existing runtime, execution, cycle, journal, or decision types.

## Tick Contract

`JournaledEMSRuntime.tick(policy, context, journal)`:

1. validates EMSPolicy, EnergySystemContext, and EventJournal inputs;
2. calls `JournaledEMSExecutionService.execute` exactly once with the exact
   supplied objects;
3. creates JournaledEMSTick from the exact returned JournaledEMSCycle; and
4. returns that immutable tick.

All validation occurs before service delegation. An invalid journal therefore
cannot cause policy evaluation.

## Identity and Exceptions

- Policy, context, and journal identities are preserved across delegation.
- The service's exact JournaledEMSCycle is stored.
- Nested context and DecisionResult identities remain unchanged.
- Empty-event execution preserves exact source journal identity.
- No downstream exception is caught, wrapped, translated, retried, or replaced.

## Statelessness and Ownership

JournaledEMSRuntime has empty slots and stores no policy, context, journal,
execution, result, history, or runtime state. It owns no repeated execution or
scheduling behavior.

## Acceptance Criteria

- Valid eventful and empty ticks follow the existing execution service.
- Invalid inputs fail before service delegation and policy evaluation.
- JournaledEMSTick is frozen, slotted, and contains exactly `execution`.
- JournaledEMSRuntime is stateless and receives only explicit dependencies.
- Existing and new runtime interfaces remain publicly importable.
- All repository quality checks pass.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
pre-commit run --all-files
~~~
