# ADR-001 — Immutable Domain Model

## Status

Accepted

## Context

EOS requires stable, replayable domain facts and decisions. Shared mutable
state, implicit timestamps, generated identifiers, or model-side I/O would
make construction nondeterministic and weaken replay guarantees.

## Decision

EOS core domain objects use Python standard-library dataclasses configured
with `frozen=True` and `slots=True`.

Identifiers and timestamps are supplied explicitly by callers. Domain objects
do not generate time, random identifiers, or external side effects.

Mapping fields receive a first-level defensive copy and expose a read-only
view. Deep freezing is deliberately outside this decision.

## Consequences

- Construction is deterministic and suitable for replay-oriented workflows.
- Accidental field assignment and first-level mapping mutation are rejected.
- Tests must provide explicit IDs and timezone-aware timestamps.
- Callers remain responsible for nested mutable values inside mappings.
- Changes require constructing a new domain object rather than mutating one.

## Alternatives Considered

- Mutable dataclasses: rejected because they permit state changes outside the
  runtime transition boundary.
- Pydantic or another model framework: rejected because the required behavior
  is small and standard-library dataclasses avoid an unnecessary dependency.
- Automatic UUID and timestamp generation: rejected because it introduces
  hidden nondeterminism.
- Recursive deep freezing: deferred because TASK-002 requires only first-level
  protection and a general deep-freeze policy would add premature complexity.
