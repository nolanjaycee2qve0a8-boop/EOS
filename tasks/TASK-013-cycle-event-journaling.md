# TASK-013 — EMS Cycle Event Journaling

## Status

IN REVIEW

## Objective

Associate one completed EMSCycle with the immutable EventJournal produced by
appending that cycle's DecisionResult events.

JournaledEMSCycle records the exact original cycle and the progressed journal.
It does not execute commands, run policies, or own runtime behavior.

## Scope

- A frozen slotted JournaledEMSCycle containing cycle and journal.
- Deterministic sequence allocation based on the journal's last record.
- One EventRecord append per DecisionResult event through EventJournal.append.
- Exact event order, event identity, cycle identity, and source-journal preservation.
- Stable public import and focused unit tests.

## Non-goals

- Command execution, journaling, conversion, or other command processing.
- Runtime loops, schedulers, timers, threads, retries, or devices.
- Clocks, timestamps, UUID generation, persistence, or communication.
- EMS algorithms, optimization, forecasting, or SOC updates.
- Changes to RuntimeKernel, TickResult, DecisionPipeline, PolicyExecutor,
  EMSCycle, EventJournal, EventRecord, or DecisionResult.
- Refactoring legacy RuntimeKernel journaling.

## Recording Contract

`JournaledEMSCycle.record(cycle, journal)`:

1. validates EMSCycle and EventJournal inputs;
2. reads only `cycle.result.events`;
3. uses sequence zero for an empty journal, otherwise last sequence plus one;
4. creates contiguous EventRecords in the original event order;
5. appends every record through EventJournal.append; and
6. returns the exact cycle with the resulting immutable journal.

An empty event tuple performs no append and preserves exact journal identity.
The finite traversal of the immutable event tuple is not a runtime loop and
does not introduce scheduling or repeated cycle execution.

## Immutability and Ownership

- JournaledEMSCycle has exactly cycle and journal fields.
- Neither cycle nor source journal is copied or mutated.
- Existing journal records and new domain Event identities are preserved.
- No policy, clock, runtime service, or infrastructure object is stored.

## Acceptance Criteria

- New sequences start at zero or the previous last sequence plus one.
- Multiple event sequences are contiguous and preserve event order.
- Original event, cycle, and existing record identities are preserved.
- The source EventJournal remains unchanged.
- Empty events preserve exact EventJournal identity.
- Commands are ignored.
- Invalid boundary types raise TypeError.
- Public imports expose EMSCycle and JournaledEMSCycle.
- All existing tests and repository quality checks pass.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
pre-commit run --all-files
~~~
