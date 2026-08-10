# TASK-093 — EMS Decision Feasibility Boundary Contract

## Objective

Create only the architecture seam between a Strategy request and an approved feasible
decision. No physical constraint algorithm is implemented.

## Architecture

```text
EMSDecision + exact DecisionProvenance
        |
        v
FeasibilityBoundary
        |
        v
FeasibleDecision
        |
        v
future BatterySimulationActuation handoff
```

## Explicit provenance input

The boundary contract is:

```text
evaluate(
    decision: EMSDecision,
    *,
    provenance: DecisionProvenance,
) -> FeasibleDecision
```

Provenance is explicit and keyword-only because the boundary must preserve the caller's
exact evidence object. Reconstructing `DecisionProvenance` from an `EMSDecision` inside the
boundary would violate TASK-092 identity requirements.

## FeasibleDecision

The frozen/slotted result stores:

- exact source `EMSDecision`;
- exact source `DecisionProvenance`;
- approved semantic `DecisionIntent`;
- finite non-negative approved raw kW magnitude.

The provenance must reference the exact source Decision. Feasibility may preserve the
source charge/discharge action or reduce it to idle, but it cannot reverse the Strategy
action and become a new business decision.

`FeasibleDecision` is not `BatterySimulationActuation` and is not a Device Command.

## Boundary

`FeasibilityBoundary` is abstract, stateless, and empty-slotted. It defines only the
evaluation interface. It owns no cache, history, Runtime state, model, device, scheduler,
or command path.

## Non-goals

- no SOC calculation or Battery physics;
- no power clipping algorithm;
- no Battery, Grid, Zero Export, TOU, or MPC constraint logic;
- no Simulator, Runtime, Device, Command, or Actuation handoff;
- no modification to Phase 5–8 or TASK-090–092 contracts.

## Validation

- abstract boundary and exact signature;
- test-only pass-through implementation;
- exact source Decision and Provenance identity;
- reconstructed equal Decision rejection;
- frozen/slotted result and empty-slotted boundary;
- action-direction and power-magnitude contract validation;
- dependency isolation, full pytest, Ruff, mypy, and diff validation.
