# TASK-106 — Optimization Core Contracts

## Objective

Create a solver-independent Optimization Layer that describes semantic
objectives, immutable optimization requests, a stateless solve seam, and a
generic outcome. This task does not implement numerical optimization.

## Architecture

```text
OptimizationObjective + OptimizationObjectiveCollection
    |
    v
OptimizationProblem (EMSContext + ForecastHorizon + objectives)
    |
    v
OptimizationBoundary.solve(problem)
    |
    v
OptimizationResult
```

## Contracts

`OptimizationObjective` describes what a future optimizer should minimize or
maximize through a semantic name and sense. It contains no executable cost
function, callback, matrix, model, solver object, or weighting algorithm.

`OptimizationObjectiveCollection` preserves the exact caller-supplied tuple
and objective identities in caller order. It does not sort, deduplicate,
normalize, score, or alter objectives.

`OptimizationProblem` holds exact references to current `EMSContext`, future
`ForecastHorizon`, and a non-empty objective collection. It is immutable and
does not merge future facts into `EMSContext`, predict Battery state, serialize
provenance, or represent solver-framework inputs.

`OptimizationBoundary` is an abstract empty-slotted seam:

```text
solve(problem: OptimizationProblem) -> OptimizationResult
```

`OptimizationResult` retains the exact `source_problem` and exposes only a
generic solver-independent outcome. It is not an `EMSDecision`, feasible
decision, `BatterySimulationActuation`, or device command.

## Responsibility separation

- Optimization: what future plan/result best serves declared objectives.
- MPC Strategy: translate a future optimization result into the current
  `EMSDecision` request through the existing Strategy architecture.
- Feasibility: decide what physical action is permitted.
- Actuation: hand an approved action to the existing Simulator layer.

No layer is bypassed by this contract introduction.

## Non-goals

- no SciPy, CVXPY, PuLP, Pyomo, OR-Tools, LP, QP, MILP, nonlinear solver, or
  optimization implementation;
- no objective weighting algorithm, Battery prediction, SOC dynamics, or
  forecast generation;
- no MPC implementation, coordinator, feasibility, actuation, simulator,
  runtime, device, PCS, dispatch, or command change;
- no modification to existing Context, Decision, Forecast, Feasibility,
  Actuation, Simulator, or Phase 5–8 contracts.

## Validation

- frozen/slotted objective, collection, problem, and result artifacts;
- exact objective tuple/order/identity preservation;
- exact Context, Horizon, objective collection, and result source-problem
  provenance;
- abstract/stateless boundary and minimal fake implementation;
- static solver/framework, Simulator, Device, and Command isolation;
- full pytest, Ruff, mypy, and diff validation.
