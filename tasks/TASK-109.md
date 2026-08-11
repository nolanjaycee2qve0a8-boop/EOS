# TASK-109 — Receding Horizon MPC Cycle Contract

## Objective

Define the immutable, traceable contract for one explicit MPC cycle. A cycle
uses one caller-supplied current context, forecast horizon, configuration,
objective collection, and strategy descriptor, then records one successful
planning outcome through one current `EMSDecision`.

## Architecture

```text
MPCCycleInput
    |
    v
MPCCycleBoundary
    |
    v
MPCCycleResult

OptimizationProblem -> OptimizationResult -> OptimizationControlPlan
    -> MPCCurrentAction -> EMSDecision
```

`MPCCycleInput` retains exact caller references. `MPCCycleResult` validates
the exact chain from input facts through the Optimization request/result, the
proposed plan, one selected current action, and the current semantic decision.

## Responsibility separation

- Optimization determines a proposed future sequence.
- `OptimizationControlPlan` represents that proposal.
- `MPCCurrentAction` identifies one current plan step only.
- `EMSDecision` is the current strategy request.
- Feasibility and Actuation remain downstream and outside this task.

Receding horizon means: solve one horizon, select its current action, emit one
current `EMSDecision`, then stop. A later caller or Runtime may create a new
input and invoke another independent cycle. TASK-109 owns no repetition.

## Non-goals

- no concrete solver, plan builder, or concrete cycle orchestrator;
- no repeated solve loop, clock, scheduler, time progression, or forecast
  refresh;
- no SOC progression, Battery physics, feasibility, clipping, or Actuation;
- no Simulator, Runtime, Device, PCS, dispatch, or Command work.

No concrete single-cycle orchestrator is added because existing frozen
`OptimizationBoundary` returns only `OptimizationResult`; it intentionally
does not define construction of an `OptimizationControlPlan`. Introducing a
plan-builder seam would be a separate architectural task.

## Validation

- immutable/slotted input and result contracts;
- exact Context, Horizon, Configuration, objectives, descriptor, Problem,
  Result, plan, selected action, and Decision provenance;
- rejection of reconstructed or foreign provenance;
- abstract empty-slotted cycle boundary and dependency isolation;
- full pytest, Ruff, mypy, and diff validation.
