# TASK-114 - Price-Aware Baseline Optimizer

## Objective

Add the first concrete deterministic optimizer that returns both a generic
`OptimizationResult` and the explicit `OptimizationSolution` associated with
that exact result, without changing `OptimizationBoundary`.

## Architecture

```text
OptimizationProblem
    |
    v
OptimizationSolutionBoundary.solve_with_solution
    |
    +--> OptimizationResult
    |
    +--> OptimizationSolution
```

`OptimizationBoundary` remains the generic result-only seam. The new
solution-producing seam makes concrete solved values explicit and preserves
`solution.source_result is result`.

## Baseline behavior

`PriceAwareBaselineOptimizer` supports only the single semantic objective
`energy_cost` with `minimize` sense. For each forecast point in supplied order:

- price at or below the configured low threshold produces `charge`;
- price at or above the configured high threshold produces `discharge`;
- an intermediate or missing price produces `idle`.

Non-idle requests use the configured positive magnitude. An empty supported
horizon produces an `optimal` result with an empty solution. Unsupported or
ambiguous objectives produce an `unavailable` result and empty solution.

## Responsibility separation

This is a deterministic price classification baseline, not LP/QP/MILP,
dynamic programming, or physically constrained scheduling. It does not use
SOC, capacity, efficiency, PV, Load, power limits, grid balance, feasibility,
Actuation, or simulation. A later caller may map the solution through the
existing control-plan builder.

## Validation

- immutable/slotted configuration, output, and abstract boundary;
- threshold and magnitude validation;
- exact Problem -> Result -> Solution provenance;
- ordered price classification, empty horizon, unsupported objective, and
  non-price fact isolation tests;
- full pytest, Ruff, mypy, and diff validation.
