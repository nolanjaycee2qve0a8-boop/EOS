# ADR-002 — Deterministic Decision Pipeline

## Status

Accepted

## Context

EOS needs a narrow deterministic boundary for applying replaceable decision
logic to immutable `Snapshot` and `Mission` inputs without introducing runtime
looping, infrastructure, or side effects.

## Decision

Use a runtime-checkable structural `DecisionPolicy` Protocol, an immutable
`DecisionResult`, and a synchronous, single-call `DecisionPipeline`.

The policy receives exactly one Snapshot and one Mission. The pipeline checks
the input, policy, and result contracts but does not generate or transform
domain outputs. Exceptions from policy code remain visible.

## Consequences

- Policy implementations remain replaceable through structural typing.
- Tests can use small policy doubles without framework inheritance.
- Pipeline execution remains deterministic and synchronous.
- Command and Event ordering and object identity are preserved.
- Policy exceptions remain available to callers for explicit handling.
- Runtime looping, persistence, publication, and EMS algorithms remain separate
  future concerns.

## Alternatives Considered

- Abstract base class: rejected because inheritance adds coupling without
  providing behavior needed by this boundary.
- Callable-only interface: rejected because a named `decide` method communicates
  the domain contract more clearly and supports runtime structural checks.
- Async pipeline: deferred because TASK-003 performs no I/O or concurrency.
- Pipeline-generated IDs or timestamps: rejected because hidden nondeterminism
  would weaken replay and caller control.
- Direct persistence or event publication: rejected because those are external
  side effects and belong outside the decision boundary.
- Full runtime implementation: deferred because orchestration loops and state
  transitions require separate architectural decisions.
