# Residential Adapter Conformance Harness — P0.8 Candidate Contract

> **DRAFT — P0.8 candidate only.** This provisional plan requires a subsequent
> user scope decision. No production implementation is authorized. It does not
> claim physical device execution, HIL, field readiness, or hardware safety.

## 1. Candidate scope

The only P0.8 direction considered here is a deterministic, test-only Adapter
Conformance Harness. It would be invoked directly by a caller with an explicit
scripted transcript and would reuse, without changing, the existing P0.7
current-caller cycle, P0.6 composition, and immutable receipt/evidence
contracts.

The candidate harness is transport-neutral and has no background work. It
would not own a command book, runtime state, adapter authority, scheduler,
clock, retry loop, or recovery store. It would never manufacture a command or
accept a historical command, safety-final request, ACK power, actual power,
trace, receipt, or transcript as new command authority.

## 2. Proposed input facts

The future caller would supply an exact approved `FeasibleDecision`, fresh
`EdgeCommandMetadata`, duration, tolerance, and an explicit finite transcript.
The transcript is proposed to comprise ordered scripted P0.4-style facts:

1. an observation fact with explicit availability;
2. for an admitted cycle only, exactly one transmission fact associated with
   the existing P0.4 request identity;
3. an ACK fact with availability and its command ID, sequence, and correlation
   ID when available; and
4. an actual-telemetry fact with explicit availability.

This list defines candidate semantics only. It does not introduce a current
production class, serializer, factory, transport message, or public import.
The transcript cannot be hydrated into an adapter, runtime, session,
continuation, handoff boundary, prepared request, or command authority.

## 3. Candidate output and fact separation

The prospective result is an audit-only conformance verdict over existing P0.7
immutable receipt/evidence. A future result shape is intentionally unspecified;
this document does not represent an implemented API. It must not emit an
executable command, continuation, adapter, runtime, request factory, or replay
capability.

P0.3 retained actual/reconciliation remains the logical execution fact. A
scripted P0.4 actual observation is a distinct adapter fact and may be compared
with reconciliation but cannot replace it. ACK correlation only says that an
available ACK corresponds to the P0.4 request; it does not prove physical
completion. Therefore a passing future conformance verdict would not prove a
PCS/BMS command executed in hardware.

## 4. Candidate fail-closed behavior

The candidate harness must reject malformed, unavailable where a required fact
is needed, out-of-order, or duplicate transcript facts. It must also reject ACK
identity/sequence/correlation mismatches, actual/reconciliation mismatches,
source/metadata identity or time mismatches, and non-admission represented as a
successful transmitted cycle. A rejected case must not return a successful
verdict, create a replacement command, retry, replay, or alter P0.7 session or
continuation consumption semantics.

For non-admission, no transmission, correlated ACK, or substituted command may
be fabricated. Any future fresh recovery remains the P0.7 caller's explicit new
session, approved decision, and metadata responsibility; it is not a harness
feature.

## 5. Frozen boundaries and non-goals

P0.1–P0.7 production, tests, public APIs, and contracts remain zero-diff under
this candidate plan. It does not authorize network, protocol, HTTP, Modbus,
CAN, serial, threading, scheduler, persistence, clock service, auto-retry,
HIL, PCS/BMS connectivity, DSP/STM32 integration, field deployment, or
hardware safety certification.

Tutorial, Demo, and leadership materials would be updated only after a future
contract and implementation have independent evidence. They are intentionally
outside this candidate-documents-only work.

## 6. Conditional future acceptance

If a later user decision authorizes implementation, acceptance would include
focused tests for normal transcripts; non-admission; unavailable facts; ACK and
actual mismatch; transcript order; exact-once behavior; fresh recovery;
source/metadata and P0.5-to-P0.3 lineage; and P0.3/P0.4 fact separation.
Future isolated mutations would need to show that deleting transcript-order,
ACK-correlation, fact-separation, or terminal-consumption guards is detected.

Publication would remain conditional on frozen-diff checks, focused and full
tests, mutation evidence, pre-commit, independent review, and explicit user
approval. None of those steps is completed or implied by this DRAFT.
