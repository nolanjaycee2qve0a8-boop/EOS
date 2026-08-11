# TASK-110 — Optimization Control Plan Construction Boundary

## Objective

Define the solver-independent seam that represents one existing
`OptimizationResult` as one EOS-standard `OptimizationControlPlan`.

## Architecture

```text
OptimizationResult
    |
    v
OptimizationControlPlanConstructionBoundary
    |
    v
OptimizationControlPlan
    |
    v
MPCCurrentAction -> EMSDecision
```

`OptimizationControlPlanConstructionInput` is immutable and retains the exact
caller-supplied result reference. A conforming boundary must return a plan whose
`source_result` is that exact object.

## Responsibility separation

- `OptimizationBoundary`: what optimization outcome was produced.
- Control-plan construction: how that outcome is represented as an EOS future
  sequence.
- `OptimizationControlPlan`: what future sequence is proposed.
- Current-action extraction: which one proposed step is current.

TASK-110 stops at `OptimizationControlPlan`; it does not extract an action,
translate an `EMSDecision`, evaluate feasibility, or hand off Actuation.

## Non-goals

- no solver or LP/QP/MILP implementation;
- no production concrete plan builder, since `OptimizationResult` carries no
  control-step data from which a plan can be manufactured;
- no MPC cycle loop, clock, scheduler, forecast refresh, or state progression;
- no Battery physics, feasibility, Actuation, Simulator, Runtime, Device, or
  Command work.

## Validation

- immutable/slotted input with exact result provenance;
- abstract, empty-slotted boundary and test-only implementation;
- exact plan source-result identity and rejection of reconstructed provenance;
- dependency isolation plus full pytest, Ruff, mypy, and diff validation.
