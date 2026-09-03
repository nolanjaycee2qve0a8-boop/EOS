# ADR-096 — DRAFT: Residential Adapter Conformance Harness

> **DRAFT — P0.8 candidate only.** This document requires a subsequent user
> scope decision. No production implementation is authorized. It is not a
> claim of physical device execution, HIL, field readiness, or hardware safety.

## Candidate decision

If subsequently authorized, P0.8 may add a **Deterministic Adapter
Conformance Harness**. It would be test-only, caller-driven, and
transport-neutral. The harness would consume an explicit deterministic
transcript of scripted observation, transmission, acknowledgement, and actual
facts while exercising the already-frozen P0.7 current-caller cycle and P0.6
composition contracts.

The candidate is a conformance consumer, not a controller or device adapter. It
does not create a command, runtime, adapter authority, prepared authority, or
real transport object. It does not add durable recovery. It must not turn a
transcript, ACK, actual fact, history, receipt, or serialized evidence into
command authority.

## Candidate input and order

The prospective caller input would contain only:

- an exact caller-approved `FeasibleDecision` and fresh caller-owned
  `EdgeCommandMetadata`, as already required by P0.5–P0.7;
- an explicit duration and tolerance; and
- an explicit, finite deterministic transcript of fact records.

This is a candidate contract description, not a new public API or type. Any
future concrete type and import surface require a later implementation decision.
The minimum proposed transcript order is: an observation fact first; for an
admitted cycle, one corresponding transmission fact next; then ACK and actual
facts with their explicit availability and correlation fields. A non-admitted
cycle must have no transmission, ACK correlation, or replacement command.

Each proposed transmission/ACK record would retain the existing P0.4 identity
and correlation facts (command ID, sequence, correlation ID, and applicable
time/provenance fields). Transcript facts remain caller-supplied scripted facts;
they are not a protocol log and do not prove a PCS/BMS physically acted.

## Candidate verdict and authority boundary

The prospective output is a conformance verdict over existing P0.7 immutable
receipt/evidence. Such a verdict would be audit-only and would not return an
executable command, a command factory, a rehydratable runtime, or a replay
entry. Whether a future interface exposes a verdict object is deliberately
unsettled; this ADR does not claim that one exists today.

P0.3 retained actual/reconciliation remains the logical execution fact. P0.4
actual is a separate scripted adapter fact and cannot replace reconciliation.
Likewise, correlated ACK is not completion evidence and a successful candidate
verdict would not establish physical execution.

Malformed or out-of-order transcript facts, unavailable facts, ACK correlation
mismatch, actual/reconciliation mismatch, source/metadata identity mismatch,
time mismatch, or non-admission must fail closed. They must not yield a
successful verdict, retry, replay, regenerated command, or continuation beyond
the P0.7 frozen consumption semantics. Continuation/session consumption and
recovery behavior remain wholly governed by P0.7; this candidate does not alter
them.

## Frozen predecessors and non-goals

P0.1–P0.7 remain frozen and would not be modified. This candidate must not add
networking, protocols, Modbus, CAN, serial, threads, schedulers, persistence,
clock services, auto-retry, HIL, PCS/BMS connectivity, DSP/STM32 work, field
deployment, or hardware safety certification. It is not an authorization to
implement a real transport or a durable recovery mechanism.

## Future validation and release gate

Only after a subsequent user scope decision, a future implementation would need
focused normal, non-admission, unavailable, ACK-mismatch, actual-mismatch,
transcript-order, exact-once, fresh-recovery, source/metadata, P0.5-to-P0.3
lineage, and P0.3/P0.4 fact-separation tests. Proposed mutations would remove
the transcript-order, ACK-correlation, fact-separation, and terminal-consumption
guards; they would need to be killed by independent assertions.

Any future release gate would be conditional on focused tests, frozen-path
checks, the full suite, mutation evidence, pre-commit, independent review, and
explicit user-approved publication. No such implementation, validation, or
release has occurred under this draft.
