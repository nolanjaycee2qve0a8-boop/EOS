# TASK-117 - Battery SOC Horizon Projection

## Objective

Add deterministic, solver-independent mathematical SOC projection for an exact
solved optimization horizon. This is planning evidence only: it neither changes
the proposed control sequence nor decides whether that sequence is feasible.

## Architecture

```text
BatteryOptimizationInput + OptimizationSolution + explicit duration
                         |
                         v
       DeterministicBatterySOCHorizonProjector
                         |
                         v
          BatterySOCHorizonProjection
```

`BatterySOCHorizonProjectionInput` preserves exact caller identities for the
battery planning input and optimization solution. The solution must originate
from the exact problem in that battery input. A projection preserves its exact
input, and each projection step preserves its exact source solution step.

## Semantics

The projector makes one caller-ordered pass. With duration in hours `dt` and
usable capacity `C`:

- charge: `delta_kwh = power_kw * dt * charge_efficiency`;
- discharge: `delta_kwh = -(power_kw * dt / discharge_efficiency)`;
- idle: `delta_kwh = 0`.

The next SOC fraction is `starting_soc_fraction + delta_kwh / C`. It is not
clamped to planning min/max or to `[0, 1]`; values outside those ranges are
evidence for later physical permission layers, not a reason to alter or reject
the solution here. Requested power is likewise not clipped to model limits.

## Non-goals

No solver, plan construction, action modification, power clipping, SOC
feasibility, actuation, simulation, runtime, device, or command behavior is
introduced. This task does not use signed simulator power semantics: direction
comes from the existing semantic `DecisionIntent` action and magnitudes stay
non-negative.

## Validation

- frozen/slotted contracts and numeric validation;
- exact problem/input/solution/step provenance;
- charge, discharge, idle, duration, capacity, continuity, empty horizon, and
  deliberately out-of-range projection coverage;
- package dependency isolation and full project checks.
