# TASK-016 — Runtime Tick Progression

## Status

IN REVIEW

## Objective

Add one explicit stateless operation that progresses from an existing
JournaledEMSTick to a new JournaledEMSTick. Progression uses the previous
tick's exact progressed EventJournal as the source for one standard runtime
tick.

## Scope

- Add `JournaledEMSRuntime.progress(previous_tick, policy, context)`.
- Validate every input before tick delegation.
- Delegate exclusively through `JournaledEMSRuntime.tick` exactly once.
- Preserve tick, policy, context, journal, EventRecord, and Event identities.
- Verify deterministic sequence progression across explicit calls.

## Progression Contract

After validating JournaledEMSTick, EMSPolicy, and EnergySystemContext,
`progress` calls:

`JournaledEMSRuntime.tick(policy, context, previous_tick.execution.journal)`

exactly once and returns the exact JournaledEMSTick produced by that call.

The operation does not copy or rebuild the previous tick, its journal, or the
returned tick.

## Sequence Behavior

- The first event in an empty journal receives sequence zero.
- Later events continue from the previous journal's last sequence plus one.
- Multiple events remain contiguous and retain their exact identities.
- Empty-event ticks preserve exact journal identity and consume no sequence.
- An event following an empty tick continues from the actual last record.

## Identity and Exceptions

- Existing EventRecord objects remain the same objects.
- Newly recorded Event objects remain the exact policy-produced objects.
- Previous ticks and journals remain unchanged.
- Tick, policy, execution, cycle, and journal exceptions propagate unchanged.
- Failed progression cannot mutate the previous tick or journal.

## Statelessness

JournaledEMSRuntime retains empty slots and stores no previous or current tick,
policy, context, journal, history, or sequence state.

## Non-goals

- Runtime or while loops, batching, iterable contexts, schedulers, or timers.
- Threads, async execution, sleep, retries, clocks, timestamps, or UUIDs.
- Commands, devices, PCS, SOC updates, persistence, communication, or telemetry.
- EMS algorithms, optimization, forecasting, or policy selection.
- Direct calls to execution, policy, cycle, record, or journal append boundaries.
- Refactoring the existing tick or legacy runtime.

## Acceptance Criteria

- Progress validates all inputs before delegation.
- Tick receives exact arguments once and its exact result is returned.
- Eventful and empty progression follows deterministic sequence rules.
- Identity and exception contracts hold across multiple explicit ticks.
- TASK-015 and all legacy runtime behavior remain unchanged.
- All repository quality checks pass.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
pre-commit run --all-files
~~~
