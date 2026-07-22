# ADR-003 — Immutable Event Journal

## Status

Accepted

## Context

EOS requires deterministic historical event tracking as a foundation for
auditability, future state reconstruction, and runtime recovery. Hidden
sequence generation, mutable storage, or infrastructure side effects would
make replay behavior less explicit and harder to verify.

## Decision

Use an immutable append-only EventJournal boundary containing ordered
EventRecord values. Each record associates an existing domain Event with a
non-negative sequence supplied explicitly by the caller.

Appending validates that sequences are unique and strictly increasing, then
returns a new journal. Replay returns the existing records in their validated
sequence order and does not reconstruct state, create events, or perform I/O.

## Consequences

- Event retrieval and replay iteration are deterministic.
- Existing journals remain stable historical values.
- Event and record identities remain available for auditability.
- The boundary supports future recovery and state reconstruction work.
- Callers remain responsible for assigning valid sequence numbers.
- Storage, serialization, retention, and runtime application remain separate.

## Alternatives Considered

- Database first: deferred because persistence technology is outside this
  boundary and would couple the kernel to infrastructure prematurely.
- Mutable event list: rejected because callers could alter recorded history.
- Event bus: rejected because delivery and publication are separate concerns.
- Automatic timestamps: rejected because Event already receives explicit times
  and replay must not introduce hidden time.
- Automatic sequence generation: rejected because the caller must own ordering
  inputs explicitly and deterministically.
