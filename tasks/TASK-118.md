# TASK-118 - Battery SOC Horizon Constraint Evaluation

## Objective

Add deterministic SOC-bound constraint evidence for one exact projected
optimization horizon and its exact battery planning model. The evaluator
answers whether every projected endpoint stays within the model's inclusive
planning SOC range; it does not alter the proposed solution.

## Architecture

```text
BatterySOCHorizonProjection + BatteryOptimizationModel
                         |
                         v
DeterministicBatterySOCHorizonConstraintEvaluator
                         |
                         v
BatterySOCHorizonConstraintEvaluation
```

The constraint input requires `battery_model is
projection.source_input.battery_input.battery_model`. Evaluation preserves the
exact input. Each violation preserves its exact `BatterySOCProjectionStep` and
records the original endpoint value, its step index, and one explicit semantic
kind: `below_min_soc` or `above_max_soc`.

## Semantics

Only each transition's ending SOC is checked. Bounds are inclusive: exactly
equal to min or max is valid. The evaluator makes one pass in projection order,
collects every violation, and never sorts, deduplicates, or stops early.

The result is feasible if and only if its tuple of violations is empty. Values
remain evidence exactly as projected: `1.16` is reported as `1.16`, and `-0.12`
is reported as `-0.12`. No SOC is clamped, no requested power is clipped, and
no power-envelope check occurs in this task.

## Responsibility separation

- SOC Projection: what mathematical SOC trajectory does a proposed solution
  produce?
- SOC Horizon Constraint Evaluation: does that trajectory meet planning SOC
  bounds?
- Optimization: what solution should be proposed?
- Strategy feasibility: is a current decision permitted downstream?

TASK-118 is optimization-horizon evidence; it does not import or reuse the
separate strategy feasibility boundary.

## Non-goals

No solution or plan replacement, action rewrite, power clipping, solver,
physical execution, actuation, simulator, runtime, device, or command behavior
is introduced.

## Validation

- frozen/slotted identity-preserving contracts;
- inclusive-bound, empty-horizon, valid, below-min, above-max, and ordered
  multi-violation coverage;
- original out-of-bound values preserved without projection or solution
  mutation;
- package dependency isolation and full project checks.
