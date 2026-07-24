# ADR-018 — Dispatched Journaled EMS Runtime Tick

## Status

Accepted

## Context

JournaledEMSRuntime produces an immutable completed tick containing the exact
policy result and progressed event journal. CommandExecutor separately owns
deterministic command submission. EOS needs an explicit runtime-facing second
phase that connects these boundaries without starting external side effects
before the completed tick exists.

Combining evaluation, journaling, and command dispatch would prevent the caller
from retaining the authoritative decision record before dispatch begins and
would blur deterministic and external side-effect boundaries.

## Decision

Introduce immutable DispatchedJournaledEMSTick with exactly one
JournaledEMSTick field, and add:

`JournaledEMSRuntime.dispatch(tick, dispatcher) -> DispatchedJournaledEMSTick`

Validate both inputs before nested access or delegation. Call
CommandExecutor.execute exactly once with the exact dispatcher and exact
DecisionResult stored in the tick. Construct the dispatched result only after
normal completion and retain the exact source tick.

Do not iterate commands, invoke dispatchers directly, execute policies, create
cycles, or journal events in runtime dispatch.

## Consequences

- Policy execution and journaling remain complete before command side effects.
- CommandExecutor remains authoritative for order, identity, empty behavior,
  and first-failure semantics.
- Source tick, execution, cycle, result, and journal identities remain intact.
- Failed dispatch leaves the caller's original tick available and unchanged.
- No receipt, status, retry, rollback, or partial-result model is introduced.
- Progression continues to operate on JournaledEMSTick independently.

## Alternatives Considered

- Add `tick_and_dispatch`: rejected because it collapses deterministic recording
  and external side effects into one call.
- Dispatch directly through CommandDispatcher: rejected because it bypasses
  CommandExecutor's deterministic orchestration contract.
- Store dispatcher or dispatch status on JournaledEMSTick: rejected because it
  would change the existing immutable decision record.
- Require a dispatched tick for progression: rejected because progression and
  external command completion remain separate concerns.
- Catch and translate failures: rejected because no error translation contract
  exists.
