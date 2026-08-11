# TASK-112 — Optimization Solution Contracts

## Objective

Add a solver-independent immutable payload that can carry concrete solved
planning values without changing generic `OptimizationResult` and without
constructing an EOS `OptimizationControlPlan`.

## Architecture

```text
OptimizationProblem
    |
    v
OptimizationBoundary
    |
    v
OptimizationResult
    |
    v
OptimizationSolution
    |
    v
future control-plan construction
    |
    v
OptimizationControlPlan
```

`OptimizationSolutionStep` represents one explicit solver-produced planning
value: a caller-supplied timestamp, semantic `DecisionIntent`, and non-negative
raw-kW magnitude. `OptimizationSolution` preserves the exact source result and
caller-supplied, strictly time-ordered tuple of those steps.

## Responsibility separation

- `OptimizationResult`: generic solve outcome with Problem provenance.
- `OptimizationSolution`: concrete solved planning values.
- Plan construction: representation of values as EOS control-plan steps.
- `OptimizationControlPlan`: proposed future EOS control sequence.

The layers are deliberately not collapsed. A solution is neither a solver, a
control plan, a current decision, feasibility approval, Actuation, nor physical
execution.

## Non-goals

- no real solver, objective function, LP/QP/MILP, MPC algorithm, or state
  equations;
- no plan construction implementation;
- no SOC/Battery physics, feasibility, Actuation, Simulator, Runtime, Device,
  or Command work.

## Validation

- immutable/slotted semantic step and solution contracts;
- finite non-negative power and action/power semantic validation;
- exact source-result, tuple, and step identity preservation;
- strict timestamp ordering and dependency isolation;
- full pytest, Ruff, mypy, and diff validation.
