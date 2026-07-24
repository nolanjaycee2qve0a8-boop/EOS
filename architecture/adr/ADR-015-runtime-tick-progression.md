# ADR-015 — Runtime Tick Progression

## Status

Accepted

## Context

JournaledEMSRuntime defines one stateless tick that receives an explicit source
journal. Callers that perform another explicit decision need a safe boundary
for using the previous tick's progressed journal without reconstructing it,
tracking sequence state separately, or bypassing the standard tick operation.

A retained runtime history or a loop would add state and scheduling behavior
outside the scope of the deterministic kernel boundary.

## Decision

Add a static `JournaledEMSRuntime.progress(previous_tick, policy, context)`
operation.

Validate JournaledEMSTick, EMSPolicy, and EnergySystemContext before any
delegation. Then call JournaledEMSRuntime.tick exactly once with the exact
policy, context, and `previous_tick.execution.journal`. Return the exact tick
produced by that call.

Progress delegates exclusively through the standard tick boundary. It does not
invoke execution services, policies, executors, cycles, event records, or
journal append operations directly. It catches no exceptions and retains no
state.

## Consequences

- Explicit callers can deterministically progress one tick at a time.
- The previous progressed journal remains the single sequence source.
- Existing records and newly produced events preserve object identity.
- Empty-event ticks retain journal identity and consume no sequence.
- Standard tick validation, execution, and journaling remain authoritative.
- Failed progressions leave the previous immutable tick and journal unchanged.
- Looping, scheduling, retries, and history ownership remain outside runtime.

## Alternatives Considered

- Pass a separately tracked journal: rejected because the previous tick already
  owns the authoritative progressed journal.
- Reimplement tick execution in progress: rejected because it would duplicate
  the standard runtime boundary.
- Store the previous tick on JournaledEMSRuntime: rejected because the runtime
  must remain stateless.
- Add batch or loop progression: rejected because this decision defines one
  explicit deterministic operation only.
- Catch and translate exceptions: rejected because no error translation
  contract exists.
