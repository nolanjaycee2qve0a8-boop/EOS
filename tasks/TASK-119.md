# TASK-119 - Battery Power Horizon Constraint Evaluation

## Objective

Add deterministic battery power-envelope evidence for one exact optimization
solution and one exact battery planning model. The evaluator answers whether
each semantic charge or discharge request exceeds its corresponding planning
power limit; it never alters the request.

## Architecture

```text
OptimizationSolution + BatteryOptimizationModel
                     |
                     v
DeterministicBatteryPowerHorizonConstraintEvaluator
                     |
                     v
BatteryPowerHorizonConstraintEvaluation
```

The input preserves exact caller references to the solution and model. Existing
contracts do not encode a stronger solution-to-model provenance relationship,
so TASK-119 deliberately does not invent one.

## Semantics

For each solution step in existing caller order:

- charge is a violation only when magnitude is greater than
  `max_charge_power_kw`;
- discharge is a violation only when magnitude is greater than
  `max_discharge_power_kw`;
- idle is non-violating because the upstream solution-step contract already
  requires a zero magnitude.

Equality with either limit is valid. Every violation preserves the exact source
step, index, semantic kind, original requested magnitude, and relevant limit.
All violations are collected in order. No requested power is clipped or changed.

## Responsibility separation

- SOC Constraint Evaluation: does a projected state trajectory violate SOC
  bounds?
- Power Constraint Evaluation: does a requested action magnitude violate a
  battery power limit?

These are independent optimization evidence channels. TASK-119 does not import
SOC projection/evaluation or the separate strategy feasibility boundary.

## Non-goals

No solution mutation, correction, plan construction, SOC projection, solver,
Actuation, simulator, Runtime, Device, or Command behavior is introduced.

## Validation

- frozen/slotted exact-reference contracts;
- inclusive directional limits, idle, empty solution, charge/discharge, and
  ordered multi-violation coverage;
- original requested magnitudes remain unchanged;
- dependency isolation and full project checks.
