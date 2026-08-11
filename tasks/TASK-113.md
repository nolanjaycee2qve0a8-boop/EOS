# TASK-113 - Optimization Solution Control Plan Builder

## Objective

Add the first production, solver-independent representation adapter from
concrete `OptimizationSolution` values to an EOS `OptimizationControlPlan`.

## Architecture

```text
OptimizationResult
    |
    v
OptimizationSolution
    |
    v
OptimizationSolutionControlPlanBuilder
    |
    v
OptimizationControlPlan
```

`OptimizationSolutionControlPlanConstructionInput` carries the exact
caller-supplied solution. Its source result remains reachable as
`solution.source_result`, avoiding duplicated provenance fields. The generic
TASK-110 construction input remains unchanged because it was intentionally
designed to carry only an `OptimizationResult`.

## Contract

The builder creates exactly one `OptimizationControlStep` for each source
solution step, in the supplied order. It retains each timestamp and exact
semantic `DecisionIntent` object, preserves the requested-power magnitude, and
returns a plan whose `source_result is solution.source_result`. An empty valid
solution becomes an empty plan.

## Responsibility separation

- `OptimizationResult`: generic solve outcome.
- `OptimizationSolution`: concrete solver-produced planning values.
- Builder: deterministic representation mapping only.
- `OptimizationControlPlan`: EOS proposed future control sequence.

The builder neither solves, evaluates objectives, predicts SOC, changes power
or action, evaluates feasibility, extracts a current action, emits an
`EMSDecision`, nor executes the plan.

## Validation

- immutable/slotted solution-aware input and abstract seam;
- one-to-one mapping, supplied order, exact intent identity, and exact result
  provenance;
- empty-plan behavior, statelessness, dependency isolation, and full project
  validation.
