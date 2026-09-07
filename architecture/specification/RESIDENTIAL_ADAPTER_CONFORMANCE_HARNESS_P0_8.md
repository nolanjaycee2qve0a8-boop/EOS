# Residential Adapter Conformance Harness — P0.8 Provisional Contract

> **LOCAL COMMIT STATUS — P0.8.** The strictly limited test-only implementation
> scope is locally committed as `993abdf` and has local validation evidence.
> Final independent publication review, user-approved PR, remote CI, and merge
> remain pending. No production capability, physical device execution, HIL,
> field readiness, or hardware safety is authorized or claimed.

## 1. Current scope

P0.8 implements a deterministic, test-only Adapter Conformance Harness. It is
invoked directly by a caller with an explicit scripted transcript and reuses,
without changing, the existing P0.7
current-caller cycle, P0.6 composition, and immutable receipt/evidence
contracts.

The harness is transport-neutral and has no background work. It does not own a
command book, runtime state, adapter authority, scheduler,
clock, retry loop, or recovery store. It would never manufacture a command or
accept a historical command, safety-final request, ACK power, actual power,
trace, receipt, or transcript as new command authority.

## 2. Current input facts

`AdapterConformanceCycleInput` requires an exact approved `FeasibleDecision`, fresh
`EdgeCommandMetadata`, duration, tolerance, and an explicit finite transcript.
The `AdapterConformanceTranscript` comprises ordered scripted P0.4-style facts:

1. an observation fact with explicit availability;
2. for an admitted cycle only, exactly one transmission fact associated with
   the existing P0.4 request identity;
3. an ACK fact with availability and its command ID, sequence, and correlation
   ID when available; and
4. an actual-telemetry fact with explicit availability.

The current public import surface is `AdapterConformanceCycleInput`,
`AdapterConformanceTranscript`, `AdapterConformanceTranscriptFact`,
`AdapterConformanceTranscriptKind`, `AdapterConformanceVerdict`, and
`DeterministicAdapterConformanceHarness`. These are provisional implementation
interfaces, not published or stable long-term APIs. They add no serializer,
factory, transport message, or transport import.
The transcript cannot be hydrated into an adapter, runtime, session,
continuation, handoff boundary, prepared request, or command authority.

## 3. Current output and fact separation

`DeterministicAdapterConformanceHarness.evaluate(...)` returns an audit-only
`AdapterConformanceVerdict` over existing P0.7 immutable receipt/evidence. It
does not emit an executable command, continuation, adapter, runtime, request
factory, or replay capability. This result remains a provisional interface and
does not claim a stable long-term API.

P0.3 retained actual/reconciliation remains the logical execution fact. A
scripted P0.4 actual observation is a distinct adapter fact and may be compared
with reconciliation but cannot replace it. ACK correlation only says that an
available ACK corresponds to the P0.4 request; it does not prove physical
completion. Therefore a passing conformance verdict does not prove a
PCS/BMS command executed in hardware.

## 4. Current fail-closed behavior

The harness rejects malformed, unavailable where a required fact
is needed, out-of-order, or duplicate transcript facts. It must also reject ACK
identity/sequence/correlation mismatches, actual/reconciliation mismatches,
source/metadata identity or time mismatches, and non-admission represented as a
successful transmitted cycle. A rejected case must not return a successful
verdict, create a replacement command, retry, replay, or alter P0.7 session or
continuation consumption semantics.

For non-admission, no transmission, correlated ACK, or substituted command is
fabricated. Fresh recovery remains the P0.7 caller's explicit new
session, approved decision, and metadata responsibility; it is not a harness
feature.

## 5. Frozen boundaries and non-goals

P0.1–P0.7 production, tests, public APIs, and contracts remain zero-diff under
this provisional implementation. It does not authorize network, protocol, HTTP, Modbus,
CAN, serial, threading, scheduler, persistence, clock service, auto-retry,
HIL, PCS/BMS connectivity, DSP/STM32 integration, field deployment, or
hardware safety certification.

Tutorial, Demo, and leadership materials remain outside this implementation
scope until independent evidence supports a separate documentation decision.

## 6. Local validation and remaining publication boundary

Local validation exercises normal transcripts; non-admission;
unavailable facts; ACK and actual mismatch; transcript order; exact-once
behavior; fresh recovery; source/metadata and P0.5-to-P0.3 lineage; and
P0.3/P0.4 fact separation. Isolated mutation evidence shows that deleting
transcript-order, ACK-correlation, fact-separation, or terminal-consumption
guards is detected.

Final independent publication review, explicit user-approved PR, remote CI,
and merge remain pending. The local commit and its validation evidence do not
imply a stable public API, production device capability, or hardware result.
