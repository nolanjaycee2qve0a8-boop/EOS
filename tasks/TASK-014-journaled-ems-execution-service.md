# TASK-014 — Journaled EMS Execution Service

## Status

IN REVIEW

## Objective

Introduce one stateless synchronous entry point that executes a supplied
EMSPolicy against an EnergySystemContext through EMSCycle, records the
completed cycle through JournaledEMSCycle, and returns the exact journaled
result.

The service composes existing boundaries. It does not reimplement their
behavior or own runtime state.

## Scope

- A stateless JournaledEMSExecutionService.
- One explicit `execute(policy, context, journal)` method.
- Complete input validation before any policy execution.
- Exact single-call delegation through EMSCycle and JournaledEMSCycle.
- Identity and downstream exception preservation.
- Stable public import and focused unit tests.

## Non-goals

- Runtime or while loops, schedulers, timers, threads, async execution, or retries.
- Clocks, timestamps, UUID generation, persistence, communication, or telemetry.
- Commands, devices, PCS, batteries, or SOC control.
- EMS algorithms, optimization, forecasting, policy registration, or selection.
- Direct calls to EMSPolicy, PolicyExecutor, EventRecord, or EventJournal.append.
- Changes to existing cycle, execution, policy, journal, decision, or runtime types.
- Refactoring legacy RuntimeKernel behavior.

## Execution Contract

`JournaledEMSExecutionService.execute(policy, context, journal)`:

1. validates EMSPolicy, EnergySystemContext, and EventJournal inputs;
2. calls `EMSCycle.execute(policy, context)` exactly once;
3. calls `JournaledEMSCycle.record(cycle, journal)` exactly once; and
4. returns the exact JournaledEMSCycle returned by recording.

All validation occurs before EMSCycle execution. In particular, an invalid
journal cannot cause policy evaluation.

## Identity and Exceptions

- The exact policy and context are passed to EMSCycle.
- The exact returned cycle and source journal are passed to recording.
- The exact JournaledEMSCycle is returned.
- Nested context, DecisionResult, and empty-event journal identities are preserved.
- No downstream exception is caught, translated, wrapped, suppressed, retried,
  or replaced.

## Statelessness and Ownership

- The service has empty slots and no instance dictionary.
- Every dependency is supplied explicitly for each call.
- It stores no policy, context, journal, cycle, result, history, or runtime state.

## Acceptance Criteria

- Valid eventful and empty executions follow existing boundary semantics.
- Both delegates are invoked exactly once with exact object identities.
- Invalid inputs fail before delegation and policy evaluation.
- Downstream exception identities propagate unchanged.
- Public imports expose JournaledEMSExecutionService and PolicyExecutor.
- All existing tests and repository quality checks pass.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
pre-commit run --all-files
~~~
