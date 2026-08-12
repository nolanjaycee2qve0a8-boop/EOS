# TASK-120 - Battery Horizon Constraint Aggregate

## Objective

Add deterministic aggregate evidence for one compatible pair of already-produced
SOC and power horizon evaluations. The aggregate reports combined battery
planning feasibility; it introduces no physical rule and does not re-run either
component evaluator.

## Architecture

```text
OptimizationSolution
    |
    +--> SOC Projection --> SOC Constraint Evaluation
    |
    +--> Power Constraint Evaluation
                       |
                       v
       Battery Horizon Constraint Aggregate
```

`BatteryHorizonConstraintInput` retains exact SOC and power evaluation
identities. It rejects pairs unless both provenance chains reach the exact same
`OptimizationSolution` and both evaluations hold the exact same
`BatteryOptimizationModel` object.

## Semantics

`BatteryHorizonConstraintEvaluation.feasible` is the logical conjunction of
component feasibility. The aggregate result stores only its exact input and the
derived boolean. Typed evidence remains separate and inspectable through:

- `source_input.soc_evaluation.violations`;
- `source_input.power_evaluation.violations`.

No generic flattened violation type is created; no violation is recreated or
mutated.

## Responsibility separation

- SOC Constraint Evaluation: state-bound evidence.
- Power Constraint Evaluation: action-magnitude evidence.
- Battery Horizon Constraint Aggregate: combined battery planning evidence.

The aggregate is not correction, optimization, or strategy feasibility. It
does not project SOC, call component evaluators, clip power, rewrite actions,
or create a solution/control plan.

## Non-goals

No new physical rule, grid/PV/load/cost rule, solver, correction, Actuation,
simulator, Runtime, Device, or Command behavior is introduced.

## Validation

- frozen/slotted exact-reference input and result;
- solution/model provenance compatibility rejection;
- complete feasibility truth table;
- typed component violations remain exact, separate, and unflattened;
- package dependency isolation and full project checks.
