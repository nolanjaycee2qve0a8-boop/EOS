# TASK-132 - Forecast-Aware PV Headroom Requirement

## Objective

Create deterministic planning evidence describing how much battery room would
be desirable for future forecast PV surplus. TASK-132 does not alter an
optimizer, current SOC, charging decision, physical revision, or simulation.

## Planning chain

```text
Forecast PV + Forecast Load
    -> future PV surplus
    -> battery-absorbable PV input
    -> stored battery energy opportunity
    -> required headroom
    -> recommended pre-PV maximum SOC
```

The public contracts are `PVHeadroomRequirementInput`,
`PVHeadroomForecastStep`, `PVHeadroomRequirement`,
`PVHeadroomRequirementBoundary`, and
`DeterministicPVHeadroomRequirementCalculator`.

## Exact calculation

For every exact caller-supplied forecast point, in caller order:

```text
pv_surplus_power_kw = max(pv_power_kw - load_power_kw, 0)
absorbable_charge_power_kw = min(pv_surplus_power_kw, max_charge_power_kw)
absorbable_input_energy_kwh = absorbable_charge_power_kw * duration_hours
stored_energy_delta_kwh = absorbable_input_energy_kwh * charge_efficiency
```

The requirement retains both total forecast PV surplus and total battery-
absorbable PV input; neither fact is collapsed into the other. Required stored
headroom is the sum of stored deltas, capped by:

```text
usable_capacity_kwh * (max_soc_fraction - min_soc_fraction)
```

The recommended pre-PV maximum SOC is `max_soc - required_headroom/capacity`,
never lower than the model minimum SOC.

## Provenance and exclusions

Each result preserves its exact input, and each step preserves the original
`ForecastPoint` identity and order. The module does not use price, current
`BatteryOptimizationState`, `DecisionIntent`, `OptimizationSolution`, SOC/power
revision, Simulator, Runtime, or device I/O.

## Horizon limitation

The TASK-131 demo retains its frozen four-point/four-hour MPC horizon. At
midnight, that horizon cannot see midday PV, so TASK-132 alone cannot prevent
the demo's overnight overcharging. A later reservation optimizer needs a
sufficiently long planning horizon and must combine this evidence with current
SOC and price.

## Non-goals

No current-SOC reservation, overnight charge suppression, target-SOC control,
MPC horizon change, new demo, MILP/QP, zero-export, export tariff, grid
constraint, curtailment, physical correction, actuation, or simulation change.
