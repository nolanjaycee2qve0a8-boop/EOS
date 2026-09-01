# ADR-093 — Residential Controlled Edge Composition Cycle

## Decision

Add `edge_runtime.controlled_composition` as a caller-driven, stateless P0.6
orchestrator.  One call accepts an exact approved `FeasibleDecision`,
caller-owned `EdgeCommandMetadata`, a P0.5 handoff boundary, an existing P0.3
`ControlledEdgeRuntime`, one P0.4 adapter and an explicit duration.  It invokes
the existing public contracts in this order:

```text
FeasibleDecision + metadata
  -> P0.5 PowerCommand handoff
  -> exact source/metadata identity gate
  -> P0.3 tick, safety/lifecycle and P0.2 reconciliation
  -> P0.4 observation, optional one-shot transmission, ACK and actual facts
  -> immutable P0.6 cycle evidence
```

P0.6 does not own a clock, thread, scheduler, retry loop, session, command
book, persistence, or cross-tick state. Its public result separates lifetimes:

- `ControlledEdgeCompositionEvidence` contains only non-executable P0.5,
  P0.3, and P0.4 facts. It retains no input, runtime, adapter, handoff boundary,
  request, factory, hydration, copy, or serialization path.
- `ControlledEdgeCompositionContinuation` contains only the exact P0.3 next
  runtime for the current caller. It has no adapter, handoff, metadata, request,
  command factory, or replay entry and is non-copyable/non-serializable. Its
  contained P0.3 runtime independently rejects copy and serialization.

Historical evidence cannot resume or recreate a cycle. The caller must pass new
P0.5 inputs explicitly for every later composition.

## Authority boundary

P0.5 remains the sole conversion from approved Feasibility power and
caller-owned identity/time metadata to `PowerCommand`. Immediately after that
handoff returns, P0.6 checks that the result retains those exact source objects
before any P0.3 logical tick or P0.4 audit operation. P0.3 remains the sole
admission, safety, lifecycle, no-replay and P0.2 logical-execution authority.
The compliant P0.5 public boundary independently enforces the same identity
contract before it returns. P0.6 retains its tick-before defence-in-depth gate
for a typed but corrupted producer result that bypasses that outer P0.5
contract; it is not evidence that compliant P0.5 fails closed inadequately.
P0.4 only consumes an already-authorized P0.3 request and returns
transport-neutral observations.

P0.3/P0.2 logical execution precedes P0.4 audit. P0.4 ACK and actual-telemetry
facts do not replace P0.3 retained actual power, create lifecycle completion,
prove physical execution, or reverse reconciliation. `MISSING` and
`UNAVAILABLE` P0.4 facts are explicit audit facts, not zero power, transmission
success, or physical completion. A malformed return, identity/origin/
transmission mismatch, or available ACK correlation mismatch fails closed with
no successful P0.6 result. P0.6 does not retry, manufacture a command, or claim
to undo the already-evaluated P0.3 logical tick.

## Consequences

P0.6 introduces no strategy, MPC, Feasibility, Actuation, Simulator, economic
or Campaign A-F change. It adds no protocol, network, I/O, thread, persistence,
HIL, PCS/BMS/STM32/DSP communication, hardware authority, field control, or
hardware-safety claim. Focused tests cover exact one-time public composition,
metadata/current-caller preservation, no admission/no replay,
evidence/continuation separation, explicit unavailable facts, malformed and
ACK-mismatch fail-close, and direct-plus-from import transport scanning. Later
mutation tests must corrupt a producer or use the public composition boundary,
never hand-construct final failure objects.
