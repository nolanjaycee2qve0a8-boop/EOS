# ADR-014 — Journaled EMS Runtime Tick

## Status

Accepted

## Context

EOS has a stateless JournaledEMSExecutionService that composes one policy
execution and deterministic event journaling. A runtime-facing boundary is
needed to represent one explicit tick without introducing a loop, scheduler,
clock, or retained runtime state.

Calling lower-level policy, executor, cycle, or journal operations from a new
runtime would duplicate responsibilities and weaken the existing ownership
boundaries.

## Decision

Introduce:

- JournaledEMSTick, an immutable slotted value containing exactly one
  JournaledEMSCycle; and
- JournaledEMSRuntime, a stateless class with empty slots and one static
  `tick(policy, context, journal)` method.

The runtime validates all inputs before execution, calls
JournaledEMSExecutionService.execute exactly once with the exact supplied
objects, and stores its exact return value in JournaledEMSTick.

Do not call EMSPolicy, PolicyExecutor, EMSCycle, JournaledEMSCycle, EventRecord,
or EventJournal.append directly. Do not catch or translate downstream
exceptions. Retain no runtime state.

## Consequences

- Callers gain one explicit runtime entry point for a completed journaled tick.
- Existing policy, execution, cycle, and journaling boundaries remain
  authoritative.
- Argument, execution, nested context, result, and empty journal identities are
  preserved.
- Invalid inputs cannot reach the service or evaluate a policy.
- Repeated execution and scheduling remain outside this boundary.

## Alternatives Considered

- Return JournaledEMSCycle directly: rejected because the runtime needs an
  explicit immutable tick result boundary.
- Reimplement cycle execution or journaling: rejected because those behaviors
  already have authoritative owners.
- Store policy or journal on the runtime: rejected because the runtime must be
  stateless.
- Add a runtime loop or scheduler: rejected because this task defines one
  deterministic execution unit only.
- Catch and wrap exceptions: rejected because no error translation contract
  exists.
