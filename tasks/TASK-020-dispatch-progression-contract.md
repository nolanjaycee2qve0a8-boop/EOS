# TASK-020 — Dispatch Progression Contract

## Status

IN REVIEW

## Objective

Add an explicit progression boundary for the recommended lifecycle in which a
JournaledEMSTick completes command dispatch before the next JournaledEMSTick is
produced.

## Scope

- Add `JournaledEMSRuntime.progress_after_dispatch`.
- Validate DispatchedJournaledEMSTick, EMSPolicy, and EnergySystemContext before
  nested access or delegation.
- Delegate exclusively through the existing `JournaledEMSRuntime.progress`.
- Pass the exact source tick, policy, and context once.
- Return the exact JournaledEMSTick produced by progression.

## Lifecycle Contract

The recommended explicit lifecycle is:

1. create a JournaledEMSTick;
2. dispatch it explicitly;
3. progress from the resulting DispatchedJournaledEMSTick; and
4. dispatch the newly produced JournaledEMSTick explicitly if required.

`progress_after_dispatch` returns a normal JournaledEMSTick. It does not
automatically dispatch the new tick.

After complete validation, the method calls:

`JournaledEMSRuntime.progress(previous_dispatch.tick, policy, context)`

exactly once and returns its exact result.

## Identity and Failure

The previous dispatched result, source tick, source journal, existing records,
policy, context, and returned tick identities are preserved across their
respective boundaries.

Progress and policy exceptions propagate unchanged. The method performs no
retry or dispatch and leaves the previous dispatched result and journal
unchanged after failure.

## Compatibility

The existing `progress` method remains valid for simulation, replay,
policy-only evaluation, and callers that deliberately progress without command
dispatch. No existing tick, progress, or dispatch behavior changes.

## Exactly-once Limitation

This contract does not guarantee exactly-once command dispatch.
JournaledEMSRuntime remains stateless, and callers can deliberately invoke
dispatch more than once for the same JournaledEMSTick.

Preventing duplicate external effects requires future idempotency keys,
dispatch receipts, processed-command storage, or adapter-level deduplication.
None of those mechanisms is introduced here.

## Non-goals

- Combined progress-and-dispatch, dispatch-and-progress, or tick-and-dispatch.
- Automatic dispatch, runtime loops, retained state, or dispatch registries.
- Exactly-once claims, idempotency stores, receipts, or processed persistence.
- Retries, timeouts, rollback, compensation, or concrete adapters.
- Command or failure events, schedulers, queues, threads, or async execution.
- Clocks, timestamps, UUIDs, telemetry, PCS, or device control.

## Acceptance Criteria

- All inputs fail fast before progression delegation.
- Progress is invoked once with exact dependencies and its exact tick is returned.
- Event and journal identity contracts continue across the lifecycle.
- Empty-command and empty-event behavior remains owned by existing boundaries.
- No dispatch or tick execution is duplicated.
- Existing direct progress remains usable.
- All repository quality checks pass.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
pre-commit run --all-files
~~~
