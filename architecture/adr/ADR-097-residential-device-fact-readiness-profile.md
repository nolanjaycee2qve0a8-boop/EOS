# ADR-097 — P0.9 Candidate Only: Residential Device-Fact Readiness Profile

> **MERGED MAIN RECORD — PR #203 CI SUCCESS.** P0.9 is a strictly limited,
> test-only local evaluator merged to repository main through PR #203 at
> `4690d47cbfa4cac0ae4eb4e9a27b722d68aa17a7`. This repository merge does not
> create a hardware, field, deployment, or stable production API claim.

> **FINAL LOCAL EVIDENCE RECORDED.** P0.1–P0.9 focused suites passed; the
> Residential frozen regression reported 530 passed and 62 deselected; Campaign
> A–F reported 62 passed in 978.15s with exit 0; and full pytest reported 2736
> passed in 716.52s with exit 0. The earlier code-stage pre-commit completed its
> four hooks with exit 0 and zero working-tree pollution. A later isolated
> pre-commit after the learning-example Ruff format edit was not PASS: its
> pytest hook reported 2587 passed and 149 errors when a relative project
> `.pytest_cache` basetemp hit Windows `WinError 5`; Ruff, format, and mypy
> passed. Seven valid current-head mutations were killed. Remote Quality checks
> then independently validated that formatting fix before PR #203 merged. None
> of this evidence establishes hardware, field, production, or release readiness.

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

This ADR retains the candidate planning history and the final local-gate facts
recorded above. The seven valid current-head mutation kills cover identity and
provenance, future timestamps, supplied ACK mismatch, missing ACK correlation
fields, actual-presence separation, fresh reassessment, and package-level
forbidden imports. Early incomplete or incorrectly-targeted attempts are not
counted as mutation evidence.

The independent final review, user-approved push, Draft PR, remote CI success,
and ordinary merge of PR #203 are complete. This historical candidate path must
not be described as deployed capability: none of these repository facts
authorize a real device connection, hardware or field control, or safety
certification. Any subsequent capability stage remains subject to a new
capability-gap review and explicit user approval.
