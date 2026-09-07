# ADR-097 — P0.9 Candidate Only: Residential Device-Fact Readiness Profile

> **PROVISIONAL LOCAL IMPLEMENTATION — NOT REVIEWED OR RELEASED.** P0.9 now has
> a strictly limited local evaluator implementation. It has not received
> independent review, mutation evidence, full-suite/pre-commit evidence, PR,
> CI, merge, or release authorization. It is not a frozen production API.

> **LOCAL EVIDENCE RECORDED.** The isolated P0.9 focused suite completed with
> 14 passed in 0.20s and exit 0. Scoped Ruff, Ruff format check, mypy, public
> import smoke, forbidden static/dynamic dependency-import scans, `git diff
> --check`, and P0.1–P0.8 frozen production-path checks passed. This local
> evidence does not establish hardware, field, production, or release readiness.

## Context

P0.4 and P0.8 define transport-neutral observation and deterministic
conformance boundaries. They deliberately do not establish whether any future
PCS/BMS device-fact source can supply the identity, availability, time, ACK,
actual, disconnect, reboot, and fresh-reassessment facts those boundaries
need. The next planning question is therefore factual readiness, not command
execution or connectivity.

## Provisional local decision

The local P0.9 readiness profile evaluates whether a caller-nominated
candidate device-fact source can meet the required P0.4/P0.8 fact semantics,
without creating command or device authority.

Its input is limited to caller-owned capability-profile data,
explicit required-fact semantics, and deterministic evidence samples. It must
not accept a `PowerCommand`, endpoint, device address, credential, socket, or
transport object.

Its output is an immutable, audit-only readiness/gap assessment:

- **PASS** explicitly records that the submitted deterministic evidence meets
  each stated requirement; it never means a physical command completed.
- **GAP** explicitly records a demonstrated missing or insufficient fact.
- Missing, conflicting, or unproven provenance, identity, availability, or
  time facts fail closed; they cannot be inferred from a previous assessment.
- Reassessment requires fresh caller-provided profile and evidence. There is
  no auto-retry, historical-evidence replay, session recovery, or continuation
  authority.

The assessment must not own or return a runtime, session, continuation,
adapter, handoff boundary, command, command factory, prepared request, or
execution authority. It cannot map an audit result to execution, transmission,
or physical completion.

## Candidate fact semantics

The provisional implementation makes the following fact dimensions explicit
and independently auditable:

| Dimension | Candidate requirement |
| --- | --- |
| Identity and provenance | Source identity, fact identity, and provenance must be explicit, consistent, and non-inferred. |
| Availability and time | Availability, observation time, freshness, and stale/unknown status must be explicit. |
| ACK correlation | ACK identity, sequence, and correlation must be demonstrably linked to the declared request fact; ACK is not physical completion. |
| Actual | Actual telemetry remains a distinct observed fact and cannot manufacture command authority or replace P0.3 reconciliation. |
| Disconnect and reboot | Disconnect, unavailable, reboot, and post-reboot identity/time discontinuities must remain explicit gaps until fresh evidence establishes the required facts. |
| Fresh reassessment | A later assessment consumes new caller evidence and never promotes earlier audit evidence to authority. |

## Frozen predecessors and non-goals

P0.1–P0.8 production contracts, Residential EMS 1.0, and Campaign A–F are
frozen dependencies. This candidate does not modify their behavior, public API,
or numerical results.

It does not authorize or implement protocol, network, HTTP, Modbus, CAN,
serial, threads, schedulers, persistence, auto-retry, HIL, PCS/BMS connection,
DSP/STM32 work, hardware control, field deployment, or hardware safety
certification.

## Consequences and future authorization gate

This ADR retains the candidate planning history. Focused and scoped static
evidence is recorded above; mutation, broader regressions, full pytest,
pre-commit, independent review, PR/CI, and a separately authorized release
decision remain required. It remains provisional and must not be described as
deployed capability.
