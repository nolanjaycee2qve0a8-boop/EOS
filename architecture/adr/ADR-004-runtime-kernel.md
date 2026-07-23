# ADR-004 — Deterministic Runtime Kernel Tick

## Status

Accepted

## Context

EOS needs a deterministic execution boundary before adding real schedulers,
timing policies, recovery behavior, and hardware integration. If the kernel
owned a loop, clock, thread, timer, or device connection at this stage, a
single decision transition would be harder to test and replay independently.

## Decision

RuntimeKernel executes exactly one explicit synchronous tick and delegates
decision logic to DecisionPipeline. It validates one Snapshot and Mission,
receives the exact DecisionResult, and progresses an immutable EventJournal by
wrapping the result Events in deterministically sequenced EventRecords.

The next sequence is derived only from existing journal state: zero for an
empty journal, otherwise the last sequence plus one. The kernel does not
generate Events, Commands, IDs, or timestamps.

## Consequences

- Runtime behavior is deterministic and directly testable.
- Scheduling and hardware remain independent external concerns.
- Existing journals and domain inputs remain unchanged.
- DecisionResult and Event identities are preserved across the tick.
- A future 100 ms loop can invoke tick externally without changing this
  orchestration boundary.
- Callers own repeated execution and carry the returned journal into a later
  kernel invocation.

## Alternatives Considered

- Internal while loop: rejected because repeated execution and shutdown policy
  belong to an external runtime host.
- Thread-based runtime: rejected because concurrency adds nondeterminism without
  serving the one-tick boundary.
- Timer ownership: rejected because clock and cadence policy are outside the
  stable kernel.
- Direct device control: rejected because protocol adapters and command
  execution belong outside decision and journal orchestration.
