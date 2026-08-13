# TASK-133 - Headroom-Aware Grid Charge Reservation

## Objective

Calculate how much caller-requested cheap-grid charging is allowed in the
current control interval without consuming the future-PV headroom described by
TASK-132. This task creates immutable reservation evidence only; it does not
change an optimizer, decision, physical revision, or demo.

## Planning chain

```text
TASK-132 recommended pre-PV maximum SOC
    + current BatteryOptimizationState
    + caller cheap-grid charge request
    -> allowed cheap-grid charge power
```

The public contracts are `HeadroomAwareGridChargeReservationInput`,
`HeadroomAwareGridChargeReservation`,
`HeadroomAwareGridChargeReservationBoundary`, and
`DeterministicHeadroomAwareGridChargeReservationCalculator`.

## Exact reservation formula

```text
target_soc = headroom_requirement.recommended_pre_pv_max_soc_fraction
available_soc_room = max(target_soc - current_soc, 0)
available_stored_energy = available_soc_room * usable_capacity_kwh
available_input_energy = available_stored_energy / charge_efficiency
soc_limited_charge_power = available_input_energy / duration_hours

allowed_grid_charge_power = min(
    requested_grid_charge_power,
    max_charge_power,
    soc_limited_charge_power,
)
```

`reservation_applied` is true exactly when allowed power is lower than the
caller request. If current SOC equals or exceeds the target, allowed cheap-grid
charge is zero. This evidence is not a generic battery-charge prohibition:
future PV-surplus charging remains a separate action and stays subject to the
existing physical revision layer.

## Provenance and exclusions

The result retains its exact input and exact TASK-132 headroom requirement. The
input requires exact identity between its battery model and the model inside the
requirement, preventing mixed planning assumptions.

The module does not inspect price, raw `ForecastHorizon`, `DecisionIntent`,
`OptimizationSolution`, Simulator, Runtime, or device I/O. The caller has
already decided that a cheap-grid request exists; TASK-133 only calculates its
headroom-preserving allowance.

## Horizon limitation

TASK-133 does not solve the frozen TASK-131 four-hour horizon limitation. If
TASK-132 cannot see midday PV from a midnight forecast, this reservation has no
midday opportunity to preserve. Future integration needs a sufficient planning
horizon before using this evidence to alter grid-charge candidates.

## Non-goals

No optimizer/demo integration, current-SOC reservation strategy, horizon change,
price threshold, PV-charge suppression, discharge logic, zero export, tariff,
MILP/QP, physical clipping, action generation, or runtime scheduling.
