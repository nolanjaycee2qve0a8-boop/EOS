# P0.11 — Residential Device-Fact Command-Correlation Audit

> **RESTRICTED LOCAL COMMIT / UNPUBLISHED.** This specification defines a
> test-only immutable audit contract. The implementation and learning-material
> integration are committed locally, but this remains neither device,
> transport, hardware, field, nor release authorization.

## 1. Purpose

P0.11 deterministically evaluates one finite caller-owned collection of inert
transmission identity, acknowledgement, actual-observation, relationship, and
assessment facts. Its sole output is immutable PASS/GAP audit evidence. A PASS
means the supplied finite facts satisfy this audit rule only; it is not command
admission, transmission success, logical execution, P0.3 reconciliation,
physical completion, device availability, or hardware readiness.

## 2. Public contract

The package `edge_runtime.device_fact_command_correlation` exposes only:

- `DeviceFactTransmissionIdentity` — explicit inert identity, sequence, origin,
  declared time, source identity, and identity epoch;
- `DeviceFactAcknowledgementObservation` — explicit ACK correlation fact and
  availability;
- `DeviceFactActualObservation` — distinct explicit actual fact and
  availability;
- `DeviceFactSourceEpochRelationship` — caller-declared expected source/epoch
  values for transmission, ACK, and actual;
- `DeviceFactCommandCorrelationInput`, finding, assessment, availability,
  status, and GAP-code contracts; and
- `DeterministicDeviceFactCommandCorrelationAuditor.evaluate`.

The evaluator is synchronous and stateless. It accepts only the input contract,
reads no clock or external state, and owns no command, runtime, adapter,
session, continuation, handoff, request, retry, scheduler, connection, or
transport authority.

## 3. Fail-closed rules

All facts must be explicit caller values. The evaluator returns GAP for:

- a missing, malformed, or historical assessment used as a fact;
- ACK or actual that is missing, unavailable, or unknown;
- mismatch of ACK identity, sequence, or origin against transmission;
- an absent declaration or a conflict between any fact's source/epoch and the
  caller-declared relationship;
- stale, future, or pre-transmission fact time; and
- reuse of assessment identity as a transmission, ACK, or actual identity.

The source/epoch relationship may declare different sources or epochs for ACK
and actual. It passes only when every observed source/epoch exactly matches the
corresponding declaration; the evaluator never infers permission from equality.

ACK and actual remain separate. Available actual does not cure missing ACK, and
available ACK does not establish actual, P0.3 reconciliation, transmission, or
physical completion.

## 4. Result and continuity boundary

An assessment contains only `assessment_identity`, `assessment_as_of`, status,
and immutable findings. It retains no input or authority reference, and cannot
hydrate, restore, factory-create, or replay an audit or command path. It may be
copied or serialized only as inert evidence; passing it to `evaluate` is
rejected.

## 5. Frozen scope and non-goals

P0.1–P0.10, Residential EMS 1.0, and Campaign A–F are zero-diff frozen. P0.11
does not change Strategy, MPC, optimizer, feasibility, actuation, Simulator,
economic accounting, P0.3 reconciliation, P0.4 observation semantics, or
P0.10 lifecycle semantics.

No protocol, network, HTTP, Modbus, CAN, serial, thread, scheduler,
persistence, retry, HIL, PCS/BMS/DSP/STM32 integration, device connection,
hardware authority, field control, safety certification, or deployment feature
is included.

## 6. Local validation and publication boundary

Completed local evidence is P0.9 focused 15 passed, P0.10 focused 28 passed,
P0.11 focused 20 passed, Edge Runtime 284 passed, Residential frozen 23
passed, Campaign A–F 62 passed in 934.67s (exit 0), full pytest 2784 passed in
550.42s (exit 0), passing static gates, and passing isolated pre-commit
ruff/format/mypy/pytest hooks (exit 0). Seven isolated mutation cases were
killed, including the package-level `ImportFrom` alias regression.

These results do not establish a push, PR, remote CI, merge, release, hardware
or field claim. Publication remains contingent on independent review and an
explicit user decision.
