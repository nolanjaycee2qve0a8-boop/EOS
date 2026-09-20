# ADR-099 — P0.11: Residential Device-Fact Command-Correlation Audit

> **RESTRICTED LOCAL COMMIT / NOT PUBLISHED OR RELEASED.** P0.11 is a
> synchronous, deterministic, test-only audit of finite caller facts. Its
> implementation and learning-material integration are committed locally only;
> they grant no device, hardware, field, transport, or release authority.

## Context

P0.9 assesses caller-supplied device-fact readiness and P0.10 assesses a finite
sequence of lifecycle-continuity facts. P0.11 adds a separate audit question:
whether one inert caller-owned transmission identity, acknowledgement fact,
actual-observation fact, and explicit source/epoch relationship are mutually
consistent at one caller-declared assessment identity and `as_of` time.

This is an evidence-correlation question. It neither admits, issues, repeats,
recovers, executes, nor completes a command. P0.3 retained actual and
reconciliation, P0.4 adapter facts, P0.8 conformance evidence, and P0.9/P0.10
assessments retain their existing meanings.

## Decision

P0.11 implements one pure evaluator over only inert values:

```text
caller transmission identity + caller ACK fact + caller actual fact
             + caller-declared source/epoch relationship
             + assessment identity / as_of
                              |
                              v
          deterministic, immutable PASS/GAP audit evidence
```

Transmission, acknowledgement, and actual facts each carry an explicit caller
source identity and identity epoch. The relationship is also explicit: it pins
the source/epoch expected for each of the three facts. Equality never implies a
relationship by inference. Missing, unavailable, malformed, stale, conflicting,
mismatched, or undeclared facts are explicit GAP findings.

The immutable assessment retains only its identity/time/status/findings. It
retains no input, fact, command, request, runtime, adapter, session,
continuation, handoff, prepared request, trace, receipt, endpoint, credential,
socket, transport, or replay authority.

## Semantics and authority boundary

- The transmission identity is a caller-owned audit subject, not a command,
  request, retry, or transmission permission.
- ACK identity, sequence, origin, source, epoch, and time are checked against
  the transmission and explicit relationship. A correlated ACK is not physical
  completion.
- Actual is a distinct caller observation. It cannot prove acknowledgement or
  transmission and cannot replace P0.3 retained actual/reconciliation.
- `assessment_identity` and `assessment_as_of` are explicit caller audit facts;
  they do not create a clock, history, or freshness inference outside the
  declared finite input.
- Historical assessment evidence is rejected as a new audit input or fact. A
  later audit requires a new caller-owned input and new explicit facts.

## Frozen predecessors and non-goals

P0.1–P0.10, Residential EMS 1.0, and Campaign A–F remain frozen. P0.11 does
not alter their behavior, APIs, numerical results, authority boundaries, or
P0.3/P0.4 facts.

P0.11 does not implement protocols, networking, HTTP, Modbus, CAN, serial,
threading, scheduling, persistence, retries, HIL, PCS/BMS/DSP/STM32
integration, hardware control, field control, safety certification, or product
deployment.

## Local validation evidence and publication boundary

The locally completed evidence is: P0.9 focused 15 passed, P0.10 focused 28
passed, P0.11 focused 20 passed, Edge Runtime 284 passed, Residential frozen
23 passed, Campaign A–F 62 passed in 934.67s (exit 0), and full pytest 2784
passed in 550.42s (exit 0). Static gates passed, isolated pre-commit's
ruff/format/mypy/pytest hooks passed (exit 0), and seven isolated mutations
were killed: source/epoch exactness, undeclared relationship, ACK
identity/sequence/origin, unavailable actual, actual-not-curing-unavailable
ACK, historical-assessment replay, and package-level `ImportFrom` alias.

This is local validation and learning-integration evidence only. P0.11 has not
been pushed, opened as a PR, reviewed by remote CI, merged, released, or
authorized for hardware or field use. Any publication still requires a separate
user decision.
