# ADR-098 — P0.10 Residential Device-Fact Lifecycle Continuity Profile

> **RESTRICTED UNCOMMITTED IMPLEMENTATION.** The user authorized a minimal,
> test-only implementation in the isolated P0.10 package. It remains
> uncommitted and unreleased. This ADR does not authorize device access,
> execution authority, publication, or hardware work; later gate results are
> recorded only after they actually occur.

## Context

P0.9 evaluates one caller-supplied `as_of` readiness snapshot. It deliberately
does not judge whether a finite sequence of independently supplied snapshots
handles lifecycle discontinuities consistently. In particular, P0.9 does not
provide a cross-snapshot audit of caller-declared disconnect, reboot,
reconnect, identity-epoch, time-discontinuity, and within-input identity-reuse facts.

The gap is evidence continuity, not command execution or connectivity. P0.3
logical reconciliation, P0.4 adapter observations, P0.8 conformance verdicts,
and P0.9 readiness PASS/GAP facts remain distinct facts with their existing
meanings.

## Restricted implementation decision

P0.10 adds a deterministic, test-only, caller-driven **Device-Fact Lifecycle
Continuity Profile**. It evaluates a finite caller-owned sequence of declared
fact snapshots under an explicit transition policy and reports immutable
PASS/GAP audit findings for lifecycle continuity only.

```text
caller-owned finite facts + explicit transition policy + explicit as_of bounds
                             |
                             v
    deterministic lifecycle-continuity qualification (test-only)
                             |
                             v
           immutable PASS/GAP audit assessment and gap records
```

The input contains only immutable caller facts, explicit
transition labels/policy, declared P0.9-style fact semantics, and explicit
time constraints. It must reject a command, endpoint, credential, socket,
adapter, runtime, session, continuation, handoff boundary, prepared request,
or command factory.

The output contains only immutable, non-executable PASS/GAP
assessment values and gap records. It cannot hold a live input, create a
command, transmission, runtime, adapter, session, continuation, replay entry,
or physical-completion claim.

## Authority and safety boundary

The evaluator owns no clock, session, continuation, runtime, handoff, adapter,
`PowerCommand`, command factory, execution authority, persistence, retry, or
background work. Every assessment is one explicit caller action over a finite
set of supplied facts; a historical assessment cannot hydrate, restore, resume,
or authorize a later assessment.

ACK remains a correlation audit fact and never proves physical completion.
Actual remains a distinct observed fact and cannot replace P0.3 reconciliation,
manufacture authority, or self-certify device execution. A PASS means only
that the explicit supplied facts meet the declared lifecycle-continuity rule.

Disconnect, reboot, reconnect, identity-epoch change, time discontinuity, or
reused within-input identity must remain explicit GAP/fail-closed facts
until the caller supplies a policy-conforming fresh fact set. It may
not infer availability, continuity, zero power, transmission success, recovery,
or physical completion from an earlier snapshot.

## Restricted implemented semantic contract

The following rules are normative for this user-authorized, uncommitted
implementation. The actual public API is limited to immutable input, snapshot,
transition, finding, assessment, and evaluator types in
`edge_runtime.device_fact_lifecycle_continuity`; this is still not release or
device authorization.

Every top-level input is one caller-owned immutable audit with
its own `assessment_identity` and `assessment_as_of`. That assessment identity
must differ from every snapshot and evidence identity within the input. Every
snapshot must be a caller-owned immutable value containing its
unique snapshot identity and evidence identity; source identity; identity
epoch; availability; `observed_at`; explicit `as_of` and maximum-age
applicability; and the independent P0.9-style required declarations for ACK
correlation and actual presence. A sequence must use a new snapshot/evidence
identity at every position. It cannot accept a `PowerCommand`, historical
assessment, adapter, runtime, session, endpoint, transport object, or any live
authority.

Each adjacent pair carries exactly one caller-declared label from this closed
set: `CONTINUITY`, `DISCONNECT`, `REBOOT`, `RECONNECT`,
`IDENTITY_EPOCH_CHANGE`, or `TIME_DISCONTINUITY`.
An absent, duplicate, or unknown label is an explicit
`UNLABELLED_OR_UNKNOWN_TRANSITION` audit GAP. The labels have these implemented
rules and exact GAP categories:

| Label | Required pair facts | Epoch/time/freshness rule | GAP when unmet or recorded |
| --- | --- | --- | --- |
| `CONTINUITY` | both snapshots are explicitly available | same source and epoch; strictly increasing `observed_at`; each satisfies caller `as_of`/max-age; new evidence identity | `CONTINUITY_FACT_MISMATCH` |
| `DISCONNECT` | next snapshot is explicitly disconnected | same source/epoch; strictly increasing time and new evidence identity | `DISCONNECT_RECORDED` |
| `REBOOT` | next snapshot explicitly records reboot | same source, different explicit epoch, strictly increasing time, new evidence identity | `REBOOT_RECORDED` |
| `RECONNECT` | may follow only `DISCONNECT`, `REBOOT`, or `IDENTITY_EPOCH_CHANGE`; next snapshot is available with complete required facts | same source, different epoch, strictly increasing time, new evidence identity | `RECONNECT_PRECONDITION_UNMET` |
| `IDENTITY_EPOCH_CHANGE` | next snapshot explicitly declares the epoch discontinuity | same source, different epoch, strictly increasing time, new evidence identity | `IDENTITY_EPOCH_DISCONTINUITY` |
| `TIME_DISCONTINUITY` | next snapshot explicitly declares a non-monotonic, future, stale, or otherwise policy-invalid time relation | new evidence identity; it may never be represented as continuity | `TIME_DISCONTINUITY_RECORDED` |

`DISCONNECT`, `REBOOT`, `IDENTITY_EPOCH_CHANGE`, and `TIME_DISCONTINUITY`
always record their exact audit GAP and also validate their documented pair
facts. A later `RECONNECT` can only document newly
supplied facts; it cannot erase, rewrite, or turn an earlier GAP into success.
Within one input, reuse of an assessment, snapshot, or evidence identity is
`ASSESSMENT_OR_EVIDENCE_IDENTITY_REUSED` GAP. The overall result is
PASS only when all evaluated transitions are structurally conformant and no GAP
record exists. Thus any finite sequence containing one of those discontinuity
labels is GAP.

The evaluator has no history, state, or global identity registry
across calls and therefore cannot prove a later call is globally “new”. A later
audit is only a distinct caller-provided top-level input. It must reject a prior
assessment/result as `HISTORICAL_ASSESSMENT_INPUT_REJECTED`; it cannot hydrate,
restore, replay, or amend an earlier result or use that result as authority.

ACK is exact correlation-only and actual is a separate presence fact. Missing,
mixed, or defaulted `None` ACK/actual declarations are
`ACK_ACTUAL_FACT_MISSING_OR_FUSED` GAPs; neither fact can prove execution,
device authority, or physical completion.

## Frozen predecessors and non-goals

P0.1–P0.9, Residential EMS 1.0, and Campaign A–F are frozen dependencies.
This candidate must not alter predecessor behavior, public APIs, or numerical
results. It is deliberately not a real device integration.

It excludes protocol, network, HTTP, Modbus, CAN, serial, thread, scheduler,
persistence, auto-retry, HIL, PCS/BMS connection, DSP/STM32 work, hardware or
field control, safety certification, and product deployment.

## Evidence gate

The implementation is authorized but this ADR claims no completed verification.
Any release proposal must show focused
continuity tests, predecessor/frozen regression, static import and scope scans,
isolated mutation evidence, independent review, publication gate, and explicit
release approval. No result in this planning document is a test, CI, mutation,
or release claim.
