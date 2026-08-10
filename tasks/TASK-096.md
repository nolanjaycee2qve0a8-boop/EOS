# TASK-096 — Zero Export Feasibility Boundary

## Objective

Add the Zero Export feasibility seam after `EMSDecision`. Zero Export is a Constraint
concern, not an EMS Strategy, and this TASK implements no physical correction algorithm.

## Architecture

```text
EMSDecision + exact DecisionProvenance
    |
    v
ZeroExportBoundary
    |
    v
ZeroExportFeasibility
```

## Result contract

`ZeroExportFeasibility` is frozen and slotted with exactly:

- exact source `EMSDecision`;
- exact source `DecisionProvenance`;
- strict Boolean `is_feasible` status.

The result records evidence only. It contains no corrected power, replacement action,
actuation, command, device instruction, or execution state.

## Boundary contract

`ZeroExportBoundary` is abstract, stateless, and empty-slotted. Its public evaluation
entry point receives the exact Decision and Provenance. Implementations provide only the
feasibility fact through `_evaluate()`.

The boundary validates with `is` that the returned result preserves both exact inputs.
Value-equal reconstructed Decisions and Provenance artifacts are not accepted as direct
lineage.

## Behavior represented

- A PV-surplus charge request may be represented as feasible and remains the exact source
  Decision because charging consumes surplus.
- A future export risk is represented only by `is_feasible=False` while preserving the
  source Decision and Provenance.

TASK-096 does not determine risk from power values and does not invent a physical
correction. Concrete evaluation belongs to a later implementation.

## Non-goals

- no modification to `SelfConsumptionStrategy`;
- no PCS clipping or Battery charge limit;
- no SOC calculation or Grid controller;
- no Zero Export control algorithm;
- no Simulator execution, Device call, Command, Runtime, or Dispatcher;
- no TOU, MPC, Optimization, or Forecasting;
- no modification to TASK-090–095 or Phase 5–8 contracts.

## Validation

- abstract/stateless boundary;
- frozen/slotted immutable result;
- exact Decision and Provenance identity;
- reconstructed artifact rejection;
- feasible charge preservation and infeasible-risk representation;
- dependency isolation, full pytest, Ruff, mypy, and diff validation.
