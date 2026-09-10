# ADR-098 — P0.10 Planning-Only Candidate: Residential Device-Fact Lifecycle Continuity Profile

> **CANDIDATE ONLY — NOT APPROVED FOR IMPLEMENTATION.** This document records a
> planning proposal after P0.1–P0.9 merged. It neither freezes a P0.10
> specification nor authorizes implementation, release, device access, or any
> execution authority.

## Context

P0.9 evaluates one caller-supplied `as_of` readiness snapshot. It deliberately
does not judge whether a finite sequence of independently supplied snapshots
handles lifecycle discontinuities consistently. In particular, P0.9 does not
provide a cross-snapshot audit of caller-declared disconnect, reboot,
reconnect, identity-epoch, time-discontinuity, and fresh-reassessment facts.

The gap is evidence continuity, not command execution or connectivity. P0.3
logical reconciliation, P0.4 adapter observations, P0.8 conformance verdicts,
and P0.9 readiness PASS/GAP facts remain distinct facts with their existing
meanings.

## Candidate decision

If separately authorized, P0.10 may add a deterministic, test-only,
caller-driven **Device-Fact Lifecycle Continuity Profile**. It would evaluate a
finite caller-owned sequence of P0.9-style declared fact snapshots under an
explicit transition policy. The candidate would report immutable PASS/GAP audit
findings for lifecycle continuity only.

```text
caller-owned finite facts + explicit transition policy + explicit as_of bounds
                             |
                             v
    deterministic lifecycle-continuity qualification (candidate only)
                             |
                             v
           immutable PASS/GAP audit assessment and gap records
```

The prospective input may contain only immutable caller facts, explicit
transition labels/policy, declared P0.9-style fact semantics, and explicit
time constraints. It must reject a command, endpoint, credential, socket,
adapter, runtime, session, continuation, handoff boundary, prepared request,
or command factory.

The prospective output may contain only immutable, non-executable PASS/GAP
assessment values and gap records. It cannot hold a live input, create a
command, transmission, runtime, adapter, session, continuation, replay entry,
or physical-completion claim.

## Candidate authority and safety boundary

The candidate owns no clock, session, continuation, runtime, handoff, adapter,
`PowerCommand`, command factory, execution authority, persistence, retry, or
background work. Every assessment is one explicit caller action over a finite
set of supplied facts; a historical assessment cannot hydrate, restore, resume,
or authorize a later assessment.

ACK remains a correlation audit fact and never proves physical completion.
Actual remains a distinct observed fact and cannot replace P0.3 reconciliation,
manufacture authority, or self-certify device execution. A PASS means only
that the explicit supplied facts meet the declared lifecycle-continuity rule.

Disconnect, reboot, reconnect, identity-epoch change, time discontinuity, or
missing fresh-reassessment evidence must remain explicit GAP/fail-closed facts
until the caller supplies a policy-conforming fresh fact set. The candidate may
not infer availability, continuity, zero power, transmission success, recovery,
or physical completion from an earlier snapshot.

## Frozen predecessors and non-goals

P0.1–P0.9, Residential EMS 1.0, and Campaign A–F are frozen dependencies.
This candidate must not alter predecessor behavior, public APIs, or numerical
results. It is deliberately not a real device integration.

It excludes protocol, network, HTTP, Modbus, CAN, serial, thread, scheduler,
persistence, auto-retry, HIL, PCS/BMS connection, DSP/STM32 work, hardware or
field control, safety certification, and product deployment.

## Authorization and evidence gate

Implementation requires a new explicit user stage authorization and a separate
frozen specification/validation contract. Any proposal must show focused
continuity tests, predecessor/frozen regression, static import and scope scans,
isolated mutation evidence, independent review, publication gate, and explicit
release approval. No result in this planning document is a test, CI, mutation,
or release claim.
