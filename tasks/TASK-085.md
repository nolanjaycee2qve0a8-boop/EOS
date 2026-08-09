# TASK-085 — Simple Battery Physics Simulation Model

Status: IN REVIEW

## Objective

Implement the first concrete Battery physics component for EOS EMS Simulator
1.0. The model realizes an explicit Battery actuation as actual power and an
immutable next SOC while preserving the existing Phase 5–7 contracts.

## Architecture

```text
BatterySimulationInput
  |- exact step identity and duration
  |- exact source BatterySimulationState
  `- exact BatterySimulationActuation
        |
        v
SimpleBatteryPhysicsModel(exact immutable BatteryParameters)
        |
        v
BatterySimulationResult
  |- exact original input
  |- immutable next state
  `- physically realized actual power
```

## Physical contract

Battery power is a finite signed raw value in kW:

- positive: charging;
- negative: discharging;
- zero: idle.

Step duration is converted from explicit seconds to hours. Capacity is raw kWh.
SOC and efficiencies are unscaled unitless fractions.

### Charging

```text
stored_energy_kwh = actual_charge_power_kw
                    * duration_hours
                    * charge_efficiency

next_soc = source_soc + stored_energy_kwh / capacity_kwh
```

Actual charging power is limited by requested power, maximum charging power, and
the energy headroom to SOC `1.0`.

### Discharging

```text
removed_energy_kwh = actual_discharge_power_kw
                     * duration_hours
                     / discharge_efficiency

next_soc = source_soc - removed_energy_kwh / capacity_kwh
```

Actual discharging power magnitude is limited by requested power, maximum
discharging power, and energy available above `reserve_soc`.

If a source SOC is already below reserve, further discharge is blocked but the
state is not silently normalized upward. Idle or fully blocked actuation
preserves the exact source-state identity.

## Identity and ownership

- `model.parameters is original_parameters`;
- `result.simulation_input is original_input`;
- the exact step, source state, actuation, and feasible-decision provenance are
  retained through the exact input;
- adjusted states are new immutable `BatterySimulationState` objects;
- the model stores no current state, result, cache, or history.

The immutable parameters are caller-supplied configuration, not retained runtime
state.

## Responsibility separation

The upstream decision and constraint layers decide and authorize an actuation.
This model does not create strategy or constraints; it physically realizes the
explicit actuation while ensuring the simulated state remains within modeled
power and SOC limits.

## Non-goals

TASK-085 does not implement SOH, degradation, temperature, cell physics, BMS,
PCS, CAN, Runtime, Device communication, Command, Dispatch, Optimization, EMS
strategy, forecast, persistence, or history.

## Validation

- charging and discharging SOC transitions;
- idle identity preservation;
- charge/discharge efficiency;
- charge/discharge power limits;
- upper SOC and reserve-SOC protection;
- explicit duration scaling;
- full exact input and feasible-decision provenance;
- deterministic repeated execution;
- frozen/slotted immutable model configuration;
- existing Phase 7 binding compatibility;
- full project quality checks.
