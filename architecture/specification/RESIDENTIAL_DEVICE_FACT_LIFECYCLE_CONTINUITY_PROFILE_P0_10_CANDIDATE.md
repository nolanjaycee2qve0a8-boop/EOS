# P0.10 Restricted Implementation — Residential Device-Fact Lifecycle Continuity Profile

> **USER-AUTHORIZED, UNCOMMITTED, AND UNRELEASED.** The names below are the
> actual minimal public API in `edge_runtime.device_fact_lifecycle_continuity`.
> This restricted test-only implementation is not a release, device-access, or
> hardware-execution authorization; no later gate is claimed as passed here.

## 1. Purpose

P0.10 audits a finite sequence of caller-owned device-fact snapshots for
lifecycle continuity across explicit disconnect, reboot, reconnect,
identity-epoch, time-discontinuity, and within-input identity-reuse rules. It
addresses the gap left intentionally by P0.9's single-`as_of` readiness
assessment. It does not connect to a device, issue a command, or execute a
cycle.

## 2. Input contract

`DeviceFactLifecycleContinuityInput` contains only:

1. a non-empty finite sequence of caller-owned immutable P0.9-style declared
   fact snapshots;
2. an explicit transition policy for every adjacent snapshot; and
3. a caller-owned immutable `assessment_identity` and `assessment_as_of`; and
4. caller-supplied time/identity-epoch constraints.

One input represents exactly one audit. Its `assessment_identity` must
differ from every snapshot/evidence identity in that input, and every sequence
position must have unique snapshot/evidence identities. Transition policy does
state, rather than infer, whether the next snapshot represents continuity,
disconnect, reboot, reconnect, identity-epoch change, or time discontinuity.

The contract rejects `PowerCommand`, raw strategy/EMS requests, endpoint,
address, credential, socket, transport, adapter, runtime, session,
continuation, handoff boundary, prepared request, command factory, ACK power,
previous actual power, trace, receipt, or historical assessment as authority.

## 3. Output contract

`DeviceFactLifecycleAssessment` is immutable and audit-only. It exposes an
overall PASS/GAP plus gap records, but does not retain evaluated snapshots or a
live input. It provides no authority, hydration-to-authority, restore, factory,
session, continuation, replay, transmission, or execution path. It may be
copied or serialized only as inert audit data and cannot restore an evaluator
or any execution authority.

PASS would mean only that the supplied finite facts conform to the explicit
candidate policy. It would not mean a command was admitted, transmitted,
acknowledged as physical completion, reconciled in P0.3, executed in hardware,
or suitable for field deployment.

## 4. Lifecycle semantics

- A disconnect, unavailable state, reboot, or identity/time discontinuity is
  an explicit GAP until policy-conforming fresh caller facts establish the next
  state.
- A reconnect cannot silently inherit a previous identity epoch, availability,
  time, ACK correlation, actual presence, or PASS result.
- Within one audit, assessment/snapshot/evidence identity reuse is an explicit
  GAP. A historical assessment output cannot be replayed as input.
- ACK remains only an exact request-correlation fact. It cannot prove actual,
  execution, or physical completion.
- Actual remains a separate observed fact. It cannot create command/device
  authority or replace P0.3 retained actual/reconciliation.
- Missing, conflicting, malformed, or unproven transition facts fail closed;
  the evaluator cannot invent defaults, zero power, success, recovery, or
  continuity.

## 5. Authority, state, and replay boundary

The evaluator is synchronous and stateless for authority purposes. It owns no
wall clock, background loop, thread, scheduler,
durable store, retry, session, continuation, runtime, adapter, handoff, or
command book. One call would consume only the explicit finite caller facts for
that audit and return only non-executable values. A later audit would require a
new caller input; there is no automatic reassessment, restoration, hydration,
or replay.

## 6. Frozen scope and non-goals

P0.1–P0.9, Residential EMS 1.0, and Campaign A–F remain zero-diff.
P0.10 adds no protocol, network, HTTP, Modbus, CAN, serial, thread,
scheduler, persistence, HIL, PCS/BMS connectivity, DSP/STM32 integration,
hardware/field control, safety certification, or product deployment. It would
not declare a stable public API.

## 7. Restricted authorization and remaining gates

The user authorized this isolated test-only module without changing P0.1–P0.9.
Focused testing, frozen-path checks, mutation evidence, independent review, and
publication gates remain separate future requirements; this document does not
claim their success.

## 8. Implemented semantic contract

Every snapshot is a caller-owned immutable value with a unique snapshot/evidence identity,
source identity, identity epoch, availability, `observed_at`, explicit
`as_of`/maximum-age applicability, exact ACK-correlation declaration, and
independent actual-presence declaration. Snapshot and evidence identities must
be new at every sequence position.

Every adjacent pair has exactly one closed-set label:
`CONTINUITY`, `DISCONNECT`, `REBOOT`, `RECONNECT`,
`IDENTITY_EPOCH_CHANGE`, or `TIME_DISCONTINUITY`. Missing, duplicated, or unknown labels produce
`UNLABELLED_OR_UNKNOWN_TRANSITION` GAP; labels are never inferred from values.

| Label | Acceptance condition | Exact audit GAP category |
| --- | --- | --- |
| `CONTINUITY` | Both available; same source/epoch; strictly increasing observed time; each meets explicit `as_of`/max-age; new evidence identity. | `CONTINUITY_FACT_MISMATCH` |
| `DISCONNECT` | Next fact explicitly disconnected; same source/epoch; strictly increasing time; new evidence identity. | `DISCONNECT_RECORDED` |
| `REBOOT` | Next fact explicitly rebooted; same source; changed explicit epoch; strictly increasing time; new evidence identity. | `REBOOT_RECORDED` |
| `RECONNECT` | Immediately follows disconnect/reboot/epoch discontinuity; next fact available with all required facts; same source but changed epoch; strictly increasing time; new evidence identity. | `RECONNECT_PRECONDITION_UNMET` |
| `IDENTITY_EPOCH_CHANGE` | Explicit discontinuity with same source, changed epoch, strictly increasing time, and new evidence identity. | `IDENTITY_EPOCH_DISCONTINUITY` |
| `TIME_DISCONTINUITY` | Explicitly identifies non-monotonic, future, stale, or policy-invalid time relation and has new evidence identity. | `TIME_DISCONTINUITY_RECORDED` |

All discontinuity labels (`DISCONNECT`, `REBOOT`,
`IDENTITY_EPOCH_CHANGE`, and `TIME_DISCONTINUITY`) are explicit GAP records;
  their pair facts are also validated and they cannot be silently recovered. `RECONNECT` only documents later
caller-supplied facts and never rewrites prior GAPs. Overall PASS
requires every transition to conform and zero GAP records. Therefore a
finite sequence containing a discontinuity label is overall GAP. Reuse of the
top-level assessment identity or any snapshot/evidence identity within that
input is `ASSESSMENT_OR_EVIDENCE_IDENTITY_REUSED` GAP.

The evaluator has no cross-call history, state, or global identity
registry, so it cannot prove that a separate later call is globally new. A
later audit must be a caller-provided independent input; a historical
assessment/result supplied as input is
`HISTORICAL_ASSESSMENT_INPUT_REJECTED` GAP and cannot hydrate, restore, replay,
or create authority.

ACK remains exact correlation-only, actual remains a distinct presence fact,
and missing, fused, or defaulted-`None` declarations are
`ACK_ACTUAL_FACT_MISSING_OR_FUSED` GAP. Neither fact proves a command,
transmission, execution, device authority, or physical completion.
