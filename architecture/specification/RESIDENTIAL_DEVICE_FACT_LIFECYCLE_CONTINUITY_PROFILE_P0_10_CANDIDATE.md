# P0.10 Planning-Only Candidate — Residential Device-Fact Lifecycle Continuity Profile

> **NOT AN IMPLEMENTED API.** The names and shapes below are prospective
> contract language for user evaluation. They are not current imports, a frozen
> specification, implementation authorization, or release authorization.

## 1. Candidate purpose

P0.10 would audit a finite sequence of caller-owned device-fact snapshots for
lifecycle continuity across explicit disconnect, reboot, reconnect,
identity-epoch, time-discontinuity, and fresh-reassessment transitions. It
addresses the gap left intentionally by P0.9's single-`as_of` readiness
assessment. It does not connect to a device, issue a command, or execute a
cycle.

## 2. Prospective input contract

A prospective `DeviceFactLifecycleContinuityInput` would contain only:

1. a non-empty finite sequence of caller-owned immutable P0.9-style declared
   fact snapshots;
2. an explicit transition policy for every adjacent snapshot; and
3. caller-supplied `as_of` and time/identity-epoch constraints.

Each snapshot would be independently bound to its caller assessment/evidence
identity. Transition policy would state, rather than infer, whether the next
snapshot represents continuity, disconnect, reboot, reconnect,
identity-epoch change, time discontinuity, or fresh reassessment.

The contract would reject `PowerCommand`, raw strategy/EMS requests, endpoint,
address, credential, socket, transport, adapter, runtime, session,
continuation, handoff boundary, prepared request, command factory, ACK power,
previous actual power, trace, receipt, or historical assessment as authority.

## 3. Prospective output contract

A prospective `DeviceFactLifecycleContinuityAssessment` would be immutable and
audit-only. It would expose an overall PASS/GAP plus per-transition gap records
and non-executable references to evaluated snapshot facts. It would not retain
live input objects or provide copy-to-authority, hydration, restore, factory,
session, continuation, replay, transmission, or execution paths.

PASS would mean only that the supplied finite facts conform to the explicit
candidate policy. It would not mean a command was admitted, transmitted,
acknowledged as physical completion, reconciled in P0.3, executed in hardware,
or suitable for field deployment.

## 4. Candidate lifecycle semantics

- A disconnect, unavailable state, reboot, or identity/time discontinuity is
  an explicit GAP until policy-conforming fresh caller facts establish the next
  state.
- A reconnect cannot silently inherit a previous identity epoch, availability,
  time, ACK correlation, actual presence, or PASS result.
- Fresh reassessment requires explicitly new caller evidence identity and
  declared facts; historical assessment output cannot be replayed as input.
- ACK remains only an exact request-correlation fact. It cannot prove actual,
  execution, or physical completion.
- Actual remains a separate observed fact. It cannot create command/device
  authority or replace P0.3 retained actual/reconciliation.
- Missing, conflicting, malformed, or unproven transition facts fail closed;
  the candidate cannot invent defaults, zero power, success, recovery, or
  continuity.

## 5. Authority, state, and replay boundary

The prospective evaluator would be synchronous and stateless for authority
purposes. It would own no wall clock, background loop, thread, scheduler,
durable store, retry, session, continuation, runtime, adapter, handoff, or
command book. One call would consume only the explicit finite caller facts for
that audit and return only non-executable values. A later audit would require a
new caller input; there is no automatic reassessment, restoration, hydration,
or replay.

## 6. Frozen scope and non-goals

P0.1–P0.9, Residential EMS 1.0, and Campaign A–F would remain zero-diff.
P0.10 would not add protocol, network, HTTP, Modbus, CAN, serial, thread,
scheduler, persistence, HIL, PCS/BMS connectivity, DSP/STM32 integration,
hardware/field control, safety certification, or product deployment. It would
not declare a stable public API.

## 7. Required approval before implementation

This candidate is feasible as a new, isolated test-only module without changing
P0.1–P0.9, but only after explicit user stage approval. That approval must
freeze the exact input/output names, transition-policy semantics, evidence
format, mutation matrix, and publication gates; it must not infer permission
from this planning draft.
