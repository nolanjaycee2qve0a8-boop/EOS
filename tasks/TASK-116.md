# TASK-116 - Battery Planning Physics Contracts

## Objective

Add solver-independent battery planning data for a future physically-aware
optimizer without changing `EMSContext`, any existing optimization path, or
the simulator's physical execution model.

## Architecture

```text
OptimizationProblem
BatteryOptimizationState
BatteryOptimizationModel
    |
    v
future physically-aware optimizer
```

`BatteryOptimizationInput` preserves the exact caller-owned Problem, current
state, and immutable model configuration. It does not merge these facts into
`EMSContext` or derive one artifact from another.

## Responsibility separation

- `EMSContext`: current strategy facts and provenance.
- `BatteryOptimizationState`: optimization-specific starting SOC only.
- `BatteryOptimizationModel`: immutable planning capacity, SOC range, power,
  and efficiency facts.
- Simulator battery model: separate physical execution model.

These artifacts are deliberately not interchangeable. TASK-116 does not
calculate future SOC, evaluate constraints, clip power, or execute a plan.

## Semantics

SOC uses normalized fractions. The model validates capacity, SOC range, power,
and efficiencies. It introduces no signed battery power: directional meaning
continues to come from semantic `DecisionIntent` actions, while magnitudes stay
non-negative in the existing planning contracts.

## Validation

- frozen/slotted state, model, and composite input;
- numeric, SOC range, power, efficiency, and boolean/non-finite rejection;
- exact Problem, state, and model identity preservation;
- dependency isolation and full project checks.
