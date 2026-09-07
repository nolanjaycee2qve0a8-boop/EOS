# ADR-096 — Residential Adapter Conformance Harness

> **LOCAL COMMIT STATUS — P0.8.** The strictly limited test-only implementation
> scope is locally committed as `993abdf` and has local validation evidence.
> Final independent publication review, user-approved PR, remote CI, and merge
> remain pending. No production capability, physical device execution, HIL,
> field readiness, or hardware safety is authorized or claimed.

## Decision

P0.8 adds a currently provisional **Deterministic Adapter Conformance Harness**
in this worktree. It is test-only, caller-driven, and transport-neutral. Its
`DeterministicAdapterConformanceHarness.evaluate(...)` consumes an explicit
deterministic transcript of scripted observation, transmission,
acknowledgement, and actual facts while exercising the frozen P0.7
current-caller cycle and P0.6 composition contracts.

The harness is a conformance consumer, not a controller or device adapter. It
does not create a command, runtime, adapter authority, prepared authority, or
real transport object. It does not add durable recovery. It must not turn a
transcript, ACK, actual fact, history, receipt, or serialized evidence into
command authority.

## Input and order

`AdapterConformanceCycleInput` currently contains only:

- an exact caller-approved `FeasibleDecision` and fresh caller-owned
  `EdgeCommandMetadata`, as already required by P0.5–P0.7;
- an explicit duration and tolerance; and
- an explicit, finite deterministic transcript of fact records.

`AdapterConformanceTranscript`, `AdapterConformanceTranscriptFact`, and
`AdapterConformanceTranscriptKind` currently represent this bounded input. The
public names are provisional implementation interfaces, not a claim of stable
long-term API. The enforced transcript order is: an observation fact first; for
an admitted cycle, one corresponding transmission fact next; then ACK and
actual facts with their explicit availability and correlation fields. A
non-admitted cycle must have no transmission, ACK correlation, or replacement
command.

Each transmission/ACK record retains the existing P0.4 identity
and correlation facts (command ID, sequence, correlation ID, and applicable
time/provenance fields). Transcript facts remain caller-supplied scripted facts;
they are not a protocol log and do not prove a PCS/BMS physically acted.

## Verdict and authority boundary

`AdapterConformanceVerdict` is the current audit-only output over existing P0.7
immutable receipt/evidence. It returns no executable command, command factory,
rehydratable runtime, or replay entry. This is a provisional implementation
interface and is not yet a published or stable long-term API.

P0.3 retained actual/reconciliation remains the logical execution fact. P0.4
actual is a separate scripted adapter fact and cannot replace reconciliation.
Likewise, correlated ACK is not completion evidence and a successful verdict
does not establish physical execution.

Malformed or out-of-order transcript facts, unavailable facts, ACK correlation
mismatch, actual/reconciliation mismatch, source/metadata identity mismatch,
time mismatch, or non-admission must fail closed. They must not yield a
successful verdict, retry, replay, regenerated command, or continuation beyond
the P0.7 frozen consumption semantics. Continuation/session consumption and
recovery behavior remain wholly governed by P0.7; this harness does not alter
them.

## Frozen predecessors and non-goals

P0.1–P0.7 remain frozen and are not modified. This harness does not add
networking, protocols, Modbus, CAN, serial, threads, schedulers, persistence,
clock services, auto-retry, HIL, PCS/BMS connectivity, DSP/STM32 work, field
deployment, or hardware safety certification. It is not an authorization to
implement a real transport or a durable recovery mechanism.

## Local validation and remaining publication gate

Local validation covers normal, non-admission, unavailable,
ACK-mismatch, actual-mismatch, transcript-order, exact-once, fresh-recovery,
source/metadata, P0.5-to-P0.3 lineage, and P0.3/P0.4 fact-separation behavior.
Isolated mutation evidence covers deletion of transcript-order,
ACK-correlation, fact-separation, and terminal-consumption guards with
independent assertions.

The remaining release boundary is final independent publication review, then
explicit user-approved PR, remote CI, and merge. No publication or merge has
occurred; the local commit and local validation do not claim a stable public
API, production capability, or hardware result.
