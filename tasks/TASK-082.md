# TASK-082 — 24-Hour Simulation Scenario and Data Input

Status: IN REVIEW

## Objective

Introduce the first EOS EMS Simulator 1.0 application-layer input contract for
one deterministic 24-hour hourly simulation.

The contract accepts caller-supplied:

- 24 explicit hourly step identities;
- a 24-value PV power curve in kW;
- a 24-value load power curve in kW;
- a 24-value tariff curve in CNY per kWh;
- immutable battery parameters;
- initial battery SOC as a raw fraction.

## Architecture

```text
caller-supplied 24-hour facts
        |
        v
DailySimulationScenarioInput
        |
        v
future application runner
        |
        v
existing Phase 6/7 SimulationScenario and execution contracts
```

`DailySimulationScenarioInput` is an application input artifact. It is not the
Phase 6 executable `SimulationScenario`: the latter requires complete component
inputs, including an explicit Battery actuation and source state. Those facts
will be assembled step by step only after the demo strategy and battery physics
exist.

## Contracts

### BatteryParameters

- `capacity_kwh`: finite, raw kWh, greater than zero;
- `max_charge_power_kw`: finite, raw kW, non-negative;
- `max_discharge_power_kw`: finite, raw kW, non-negative;
- `charge_efficiency`: raw unitless fraction in `(0, 1]`;
- `discharge_efficiency`: raw unitless fraction in `(0, 1]`;
- `reserve_soc`: raw unitless fraction in `[0, 1]`.

### DailySimulationScenarioInput

- every curve is an exact caller-supplied tuple with exactly 24 values;
- PV and load values are finite, non-negative raw kW;
- tariff values are finite signed CNY per kWh with no hidden scaling;
- `initial_soc` is a raw unitless fraction in `[0, 1]`;
- step sequences are exactly `0..23` in caller order;
- every duration is exactly 3600 seconds;
- every timestamp is explicit, timezone-aware, and consecutive by one hour;
- exact tuple, step, and battery-parameter references are preserved.

Validation does not sort, normalize, copy, reconstruct, or generate facts.

## Non-goals

TASK-082 does not add:

- PV or Load model execution;
- EMS strategy or intent generation;
- battery physics, SOC transition, or power limiting;
- grid energy balance;
- a simulation runner or automatic progression;
- CSV export or plotting;
- Runtime, Scheduler, Device, Command, Dispatch, Optimization, Forecast, or AI.

It does not modify any Phase 5, Phase 6, or Phase 7 contract.

## Validation

- focused unit tests;
- `pytest`;
- `ruff check .`;
- `ruff format --check .`;
- `mypy .`;
- `pre-commit run --all-files`.
