# TASK-027 — Energy System State Boundary

## Status

IN REVIEW

## Purpose

Introduce immutable physical component state models and one
`EnergySystemState` aggregate for future EMS decisions.

The boundary records facts supplied by callers. It does not calculate state,
forecast generation, optimize energy, dispatch commands, or control devices.

## Architecture

~~~text
Physical system
        |
        v
EnergySystemState
        |
        v
DecisionContext
        |
        v
Future EMS Policy
        |
        v
DecisionResult
~~~

TASK-027 does not assemble `DecisionContext` and does not modify runtime,
policy, dispatch, audit, trace, replay, or explanation layers.

## Package Boundary

TASK-007's `kernel.state` models remain asset-scoped operational observations
identified by `asset_id`. TASK-027 introduces the separate
`kernel.system_state` package for one physical system snapshot. Existing public
imports and behavior are unchanged.

## Models and Contracts

### BatteryState

- `soc`: unitless fraction in `[0, 1]`.
- `soh`: unitless fraction in `[0, 1]`.
- `voltage_v`: non-negative V.
- `current_a`: signed finite A.
- `temperature_c`: signed finite degrees Celsius.
- `available_charge_power_kw`: non-negative kW.
- `available_discharge_power_kw`: non-negative kW.

### PCSState

- `active_power_kw`: signed finite kW.
  - positive means AC output to the load or grid;
  - negative means AC absorption from the grid or battery side;
  - zero means no active AC power exchange.
- `reactive_power_kvar`: signed finite kVAr.
- `operating_state`: non-empty factual label.
- `fault_state`: non-empty factual label.

State labels are observations, not enums or control commands.

### PVState

- `available_power_kw`: non-negative kW.
- `actual_power_kw`: non-negative kW.

No MPPT or forecast behavior is included.

### GridState

- `grid_power_kw`: signed finite kW.
  - positive means importing power from the grid;
  - negative means exporting power to the grid;
  - zero means balanced grid exchange.
- `voltage_v`: non-negative V.
- `frequency_hz`: positive Hz.

### EnergySystemState

The aggregate exposes exactly four component fields:

- `battery`: the original `BatteryState`.
- `pcs`: the original `PCSState`.
- `pv`: the original `PVState`.
- `grid`: the original `GridState`.

Each field contains the exact object supplied by the caller. The aggregate does
not copy, serialize, reconstruct, sort, or normalize component objects. No
compatibility aliases are provided.

## Immutability

Every model is a frozen, slotted dataclass. No model owns a list, dictionary,
set, cache, history, runtime, or mutable public collection.

## Non-goals

- EMS policy, optimization, or forecasting.
- Scheduling, dispatch, command execution, or device control.
- MPPT, battery calculation, or PCS behavior.
- Runtime ownership or communication dependencies.
- Persistence, telemetry, caches, or history.

## Validation

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
~~~
