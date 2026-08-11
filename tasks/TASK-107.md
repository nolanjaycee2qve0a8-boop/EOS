# TASK-107 — Optimization Control Plan Contract

## Objective

Introduce solver-independent immutable artifacts for a proposed future control
sequence. This task models what a future optimization process proposes; it does
not execute the sequence or implement a solver.

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
OptimizationControlPlan
    |
    v
Future MPC Strategy
    |
    v
current EMSDecision
    |
    v
Feasibility -> Actuation -> Simulator
```

## Contracts

`OptimizationControlStep` has one explicit timezone-aware future timestamp,
one existing semantic `DecisionIntent` (`charge`, `discharge`, or `idle`), and
one finite non-negative raw-kW requested magnitude. Charge and discharge
require positive power; idle requires zero. Direction remains semantic in the
intent, never as a signed generic planning power.

`OptimizationControlPlan` preserves exact identity to its source
`OptimizationResult` and an exact caller-supplied tuple of steps. Step order is
caller-defined and must be strictly increasing by explicit timestamp. The plan
does not create timestamps, sort, deduplicate, advance a horizon, or continue
to another step automatically. An empty finite sequence is valid.

## Separation of responsibilities

- `OptimizationResult`: outcome of solving an immutable optimization request.
- `OptimizationControlPlan`: proposed future control sequence.
- `EMSDecision`: only the current semantic action requested by an MPC Strategy.
- Feasibility: physical permission for that current request.
- Actuation: handoff to existing simulation execution.

The plan is not a physical instruction and never directly becomes an actuation
or command.

## Non-goals

- no solver, SciPy, CVXPY, PuLP, Pyomo, OR-Tools, LP, QP, MILP, or nonlinear
  optimization;
- no MPC implementation, receding-horizon loop, SOC dynamics, Battery physics,
  feasibility calculation, or power clipping;
- no Simulator execution, runtime, device, PCS, dispatch, or command work;
- no modification to EMSContext, EMSDecision, Forecast, MPC, Optimization
  objective, Feasibility, Actuation, or Simulator contracts.

## Validation

- immutable/slotted valid charge, discharge, and idle steps;
- invalid power, action/power consistency, and timestamp validation;
- exact source-result, tuple, and step identity preservation;
- strict caller-supplied timestamp ordering;
- static Solver, Simulator, Device, and Command dependency isolation;
- full pytest, Ruff, mypy, and diff validation.
