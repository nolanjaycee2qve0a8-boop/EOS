# TASK-002 — Immutable Domain Objects

## Status

IN REVIEW

## Objective

Define the immutable `Snapshot`, `Mission`, `Command`, and `Event` objects that
form the initial EOS kernel domain vocabulary.

## Scope

- String-based, caller-supplied identity types.
- Frozen, slotted standard-library dataclasses.
- Shared validation for identifiers, timestamps, integers, and mappings.
- Public imports from `kernel.domain` and `kernel.ids`.
- Deterministic unit tests using fixed identifiers and timestamps.

## Non-goals

- EMS scheduling or optimization algorithms.
- Runtime loops or state machines.
- Event journals, replay implementation, or persistence.
- APIs, device protocols, forecasting, AI, or capability behavior.

## Acceptance Criteria

- All four objects are immutable and support dataclass value equality.
- All timestamps are explicitly supplied and timezone-aware.
- All identifiers are explicitly supplied and non-empty.
- Mapping fields are shallow defensive copies exposed as read-only mappings.
- Public import surfaces and validation failures are covered by unit tests.
- The repository quality checks and GitHub Actions pass.

## Validation Commands

```bash
pytest
ruff check .
ruff format --check .
mypy .
pre-commit run --all-files
```

## Implementation Notes

The objects use `@dataclass(frozen=True, slots=True)`. Validation occurs in
`__post_init__`, with `object.__setattr__` used only to write validated or
frozen values back during construction. No object reads the clock, creates an
identifier, or performs external I/O.
