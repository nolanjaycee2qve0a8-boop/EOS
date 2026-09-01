# Residential Controlled Edge Composition — P0.6

## Scope

P0.6 is one explicit, caller-driven composition cycle.  It composes frozen
P0.5 command handoff, P0.3 controlled-runtime execution evidence and P0.4
transport-neutral adapter evidence without changing any predecessor contract.

```text
caller-approved FeasibleDecision + EdgeCommandMetadata
        -> EdgeCommandHandoffResult
        -> ControlledEdgeRuntime.tick(command)
        -> RuntimeLoopStep
        -> DeviceAdapterStepEvidence
        -> ControlledEdgeCompositionResult(evidence, continuation)
```

## Inputs and identity

`ControlledEdgeCompositionInput` accepts only an exact `FeasibleDecision`,
exact `EdgeCommandMetadata`, an `EdgeCommandHandoffBoundary`, existing
`ControlledEdgeRuntime`, `ResidentialDeviceAdapterBoundary`, positive duration
and non-negative tolerance.  The P0.5 result must retain the exact decision and
metadata objects. P0.6 checks that exact identity immediately after P0.5
handoff returns and before any P0.3 logical tick or P0.4 audit call; a mismatch
raises fail-closed and does not claim to undo an already-executed tick. P0.6
creates no identity, sequence, issue time, validity window, reason, source or
correlation field.

The compliant P0.5 public `handoff()` boundary already verifies those exact
objects before returning its result. P0.6 repeats the check as a pre-execution
defence-in-depth boundary for a type-correct result supplied by a corrupted
producer that bypassed P0.5's outer contract. The P0.6 focused harness directly
overrides public `handoff()` for this corruption case; it does not treat a
P0.5 outer-boundary rejection as P0.6 evidence.

The P0.3 caller command must be the exact P0.5 command object.  If P0.3 admits
it, its admitted command must be that same object and have
`current_caller` origin.  P0.4 transmission is then derived only through the
public `P03DeviceAdapterIntegration` from that caller/admitted command and the
retained P0.3 safety decision. All request identity/time fields and
safety-final power/mode are independently checked in the immutable result.

The result contains non-executable `evidence` and a current-caller
`continuation`. Evidence contains P0.5, P0.3, and P0.4 facts only; it has no
source input, live runtime, adapter, handoff boundary, or request. Continuation
has only the exact P0.3 next runtime. Neither contract supports copy, pickle,
hydration, factory, or command replay; the contained P0.3 runtime independently
rejects copy and serialization too.

## Runtime and adapter facts

P0.3 performs its own one-shot P0.2 logical execution before P0.4 audit
operations. P0.6 always collects P0.4 observation, ACK observation, and actual
telemetry observation. It transmits exactly once only if P0.3 actually admitted
the current caller command. Missing admission means no request, no transmission,
and no correlated ACK. A later P0.4 fact cannot reverse or overwrite P0.3
reconciliation.

P0.4 actual telemetry is a separate physical observation.  It is not fed into
the already-completed P0.3/P0.2 reconciliation and cannot claim completion.
Likewise, ACK correlation proves only that an available ACK refers to the
P0.4 request; it never proves actual execution.  This explicit separation is
intentional in the current deterministic composition prototype.

## Fail-closed and exclusions

`MISSING` and `UNAVAILABLE` P0.4 facts return as explicit audit evidence. They
do not mean physical completion, zero power, transmission success, or lifecycle
completion. A malformed adapter fact, unexpected boundary type, mismatched ACK,
missing retained P0.3 safety decision, illegal P0.3 origin, or transmission
mismatch raises instead of returning a successful result. The error does not
claim to undo the already-completed logical tick. P0.6 has no recovery, retry,
scheduling, persistence, serialization/hydration authority, or command replay.
It does not accept raw strategy/EMS requests, trace evidence, ACK power, or
previous actual power as command authority.

P0.6 is not device protocol, I/O, network, HIL, firmware, hardware safety,
field deployment or production Runtime functionality. Focused validation uses:

```powershell
$env:PYTHONPATH=(Get-Location).Path
pytest tests/unit/edge_runtime/test_controlled_composition.py
```

It is followed by scoped Ruff/format/mypy/import/scope and frozen-path checks.
Upstream/full, mutation execution, independent review, and publication remain
later gates. Mutations must use public composition or producer corruption plus
independent validation, never a hand-constructed final failure result.
