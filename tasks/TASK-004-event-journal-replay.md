# TASK-004 — Event Journal and Deterministic Replay Boundary

## Status

IN REVIEW

## Objective

Establish the first EOS event journal boundary for ordered immutable event
storage, deterministic retrieval, and basic replay iteration.

## Scope

- An immutable EventRecord pairing a caller-supplied sequence with an Event.
- An immutable append-only EventJournal.
- A synchronous replay boundary returning existing records in sequence order.
- Focused validation, public imports, and deterministic unit tests.

## Non-goals

- State reconstruction, runtime recovery implementation, or a state machine.
- Database or filesystem persistence and serialization formats.
- Event buses, message queues, networking, or cloud synchronization.
- Runtime loops, command execution, async processing, or distributed systems.
- EMS scheduling, optimization, forecasting, or control algorithms.
- Automatic sequences, timestamps, identifiers, or event creation.

## Architecture

EventRecord associates an explicit non-negative sequence with an existing
immutable domain Event. EventJournal stores records as a tuple and enforces
strictly increasing unique sequences when returning a new journal from append.
Replay exposes those exact records without mutation or state reconstruction.

## Acceptance Criteria

- EventRecord and EventJournal use frozen slotted dataclasses.
- Invalid types raise TypeError and invalid values raise ValueError.
- Append preserves the original journal and returns a new journal.
- Records remain ordered, unique by sequence, and externally immutable.
- Replay preserves record and Event identity without creating domain objects.
- All existing tests and repository quality checks pass.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
pre-commit run --all-files
~~~

## Implementation Notes

Sequences are supplied by callers and are never generated or renumbered.
Journal ordering is established at append time, so replay is a direct immutable
read boundary. Persistence, serialization, publication, runtime state
transitions, and recovery behavior remain future architectural decisions.
