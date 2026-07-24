# ADR-019 — Dispatch Progression Contract

## Status

Accepted

## Context

EOS separates deterministic policy evaluation and event journaling from
external command dispatch. After dispatch succeeds, callers need an explicit
way to express the recommended lifecycle before producing the next tick,
without changing the existing direct progression boundary.

Requiring callers to extract and pass the nested source tick themselves weakens
the lifecycle signal. Combining progression and dispatch would instead collapse
separate ownership boundaries and introduce side effects into progression.

## Decision

Add:

`JournaledEMSRuntime.progress_after_dispatch(previous_dispatch, policy, context)`

Validate DispatchedJournaledEMSTick, EMSPolicy, and EnergySystemContext before
nested access. Delegate exactly once and exclusively through:

`JournaledEMSRuntime.progress(previous_dispatch.tick, policy, context)`

Pass exact objects and return the exact resulting JournaledEMSTick. Do not
dispatch the new tick, call lower-level execution boundaries, catch exceptions,
or retain state.

Keep `JournaledEMSRuntime.progress` unchanged and independently usable.

## Consequences

- The recommended dispatch-before-progression lifecycle becomes explicit.
- Existing direct progression remains available for simulation, replay, and
  policy-only use.
- Source tick, journal, record, policy, context, and next-tick identities remain
  intact.
- Empty command and event behavior remains owned by existing boundaries.
- Progress or policy failures leave the previous immutable lifecycle state
  available and unchanged.
- Each new tick still requires a separate explicit dispatch call.

## Exactly-once Limitation

This decision does not guarantee exactly-once command dispatch. The runtime is
stateless, and a caller may dispatch the same JournaledEMSTick more than once.

True duplicate-effect prevention requires future idempotency keys, dispatch
receipts, processed-command storage, or adapter-level deduplication. These
mechanisms are deliberately deferred.

## Alternatives Considered

- Replace direct progress: rejected because simulation and replay do not require
  command dispatch.
- Automatically dispatch the next tick: rejected because progression must not
  own external side effects.
- Add a combined dispatch-and-progress method: rejected because failure and
  ownership boundaries would become ambiguous.
- Track dispatched ticks in runtime state: rejected because JournaledEMSRuntime
  must remain stateless.
- Claim exactly-once behavior from the wrapper type: rejected because a type
  alone cannot prevent repeated external effects.
