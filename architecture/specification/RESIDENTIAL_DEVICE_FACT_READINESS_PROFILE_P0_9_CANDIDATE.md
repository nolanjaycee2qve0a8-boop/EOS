# P0.9 Provisional Local Implementation — Residential Device-Fact Readiness Profile

> **PROVISIONAL LOCAL IMPLEMENTATION — NOT REVIEWED OR RELEASED.** This
> specification records a limited local evaluator and focused-test contract. It
> is not release authorization, a frozen P0.9 scope, a stable public API, or
> evidence of independent review, mutation, full-suite/pre-commit, PR, CI, or
> merge success.

> **LOCAL EVIDENCE RECORDED.** Isolated focused validation completed with 14
> passed in 0.20s and exit 0. Scoped Ruff, Ruff format check, mypy, public
> import smoke, forbidden static/dynamic dependency-import scans, `git diff
> --check`, and P0.1–P0.8 frozen production-path checks passed. These facts do
> not establish release, hardware, field, or production readiness.

## 1. Local purpose

Evaluate whether a candidate PCS/BMS device-fact source, described only by
caller-owned capability data and deterministic evidence samples, satisfies the
identity, availability, time, ACK-correlation, actual, disconnect/reboot, and
fresh-reassessment semantics required by the P0.4/P0.8 boundaries—without
creating command or device authority.

## 2. Input contract

The caller supplies all of the following explicitly:

1. a caller-owned capability profile identifying declared fact capabilities;
2. an explicit set of required fact semantics; and
3. finite deterministic evidence samples for those requirements.

The input contract rejects `PowerCommand`, an endpoint, device
address, credential, socket, adapter, runtime, session, handoff boundary,
prepared request, command factory, or serialized authority. It is an evidence
profile, not a transport or execution request.

## 3. Output contract

The result is immutable and audit-only. It may report a requirement
as explicit **PASS** or explicit **GAP**, together with non-executable evidence
references and gap reasons. It must not contain a live input reference or any
hydration, factory, copy, serialization, replay, continuation, adapter,
handoff, runtime, session, or command authority.

PASS means only that the caller-provided deterministic samples demonstrate the
stated semantic requirement. It is not an ACK, transmission, logical execution,
physical completion, hardware qualification, or field-readiness assertion.

## 4. Required semantic assessments

| Required fact | Local assessment rule |
| --- | --- |
| Identity and provenance | Require explicit, internally consistent source and fact identity plus provenance. Missing or conflicting claims are GAP/fail-closed. |
| Availability and time | Require explicit availability, timestamps, freshness, and stale/unknown meaning. Absence of proof is not inferred as available or fresh. |
| ACK correlation | Require exact declared request correlation facts. A correlated ACK remains an audit fact and never establishes physical completion. |
| Actual telemetry | Preserve actual as a separate observed fact. It never creates command authority and cannot replace P0.3 retained actual/reconciliation. |
| Disconnect and reboot | Record disconnect, unavailability, reboot, identity changes, and time discontinuities as explicit gaps until new evidence proves the required semantics. |
| Fresh reassessment | Require a fresh caller profile and evidence set. Historical assessment/evidence cannot retry, resume, or authorize a new assessment. |

Malformed, missing, conflicting, or unproven required facts fail closed. A
candidate assessment must neither manufacture defaults nor reinterpret absence
as zero power, success, ACK, actual, execution, or recovery.

## 5. Authority and lifecycle boundary

The evaluator is stateless for authority purposes. It owns no clock,
thread, scheduler, session, durable store, retry loop, adapter, transport, or
device connection. Evidence has no command or device authority. Historical
evidence cannot be replayed into an assessment; each assessment is a fresh
caller action with fresh deterministic inputs.

P0.3 logical reconciliation, P0.4 audit observations, and P0.8 conformance
evidence retain their existing distinct meanings. This candidate cannot revise,
replace, or reverse any of them.

## 6. Frozen dependencies and explicit non-goals

P0.1–P0.8 production contracts, Residential EMS 1.0, and Campaign A–F remain
unchanged dependencies. No existing predecessor behavior or public API may be
altered by a future P0.9 proposal without separate authorization.

This candidate excludes protocol, network, HTTP, Modbus, CAN, serial,
threading, scheduler, persistence, auto-retry, HIL, PCS/BMS connection,
DSP/STM32 integration, hardware authority, field deployment, and safety
certification.

## 7. Remaining release decision

The planning decision authorizes this local, test-only evaluator only. It does
not authorize a stable public API, external evidence source, real device
connection, or release. Focused/scoped-static evidence is recorded above;
mutation, broader regression, full pytest, pre-commit, independent review,
PR/CI, and a separately approved release remain required.
