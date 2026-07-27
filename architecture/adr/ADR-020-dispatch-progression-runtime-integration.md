# ADR-020 — Dispatch Progression Runtime Integration

## Status

Accepted

## Context

EOS already owns deterministic behavior in separate boundaries for journaled
ticks, command dispatch, and dispatch-before-progression. Applications need a
single explicit entry point for one complete lifecycle without reimplementing
or bypassing those boundaries.

The integration must preserve the two-phase external side-effect contract:
the journaled tick exists before command dispatch, and progression begins only
after dispatch succeeds.

## Decision

Introduce stateless DispatchProgressionRuntime with one static `execute`
operation.

Validate every current and next-stage dependency before execution. Compose the
existing boundaries in strict order:

1. `JournaledEMSRuntime.tick`;
2. `JournaledEMSRuntime.dispatch`;
3. `JournaledEMSRuntime.progress_after_dispatch`.

Invoke each exactly once, pass exact intermediate identities, and return the
exact JournaledEMSTick produced by progression. Catch no exceptions and retain
no state.

## Consequences

- Applications gain one deterministic lifecycle integration entry point.
- Existing runtime boundaries remain authoritative and independently usable.
- Decision failure prevents external dispatch.
- Dispatch failure prevents next-tick progression.
- Context, result, journal, record, command, and tick identities remain intact.
- No retry, timeout, persistence, device adapter, or runtime cache is added.

## Alternatives Considered

- Reimplement the three stages: rejected because it would duplicate established
  kernel ownership.
- Dispatch before journaled tick completion: rejected because external effects
  must begin only after the decision record exists.
- Progress after a failed dispatch: rejected because it violates the recommended
  lifecycle contract.
- Store intermediate lifecycle state: rejected because the integration must be
  stateless.
