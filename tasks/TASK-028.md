# TASK-028 — DecisionContext Assembly Boundary

## Status

IN REVIEW

## Objective

Introduce a deterministic, stateless boundary that assembles one immutable
`DecisionContext` from an `EnergySystemState` and explicit decision facts.

Assembly connects existing contracts. It does not extend the physical state
model or introduce EMS behavior.

## Architecture

~~~text
EnergySystemState
        |
        v
DecisionContextAssembler
        |
        v
DecisionContext
        |
        v
Future EMS Policy
~~~

## Assembly Contract

`DecisionContextAssembler.assemble()` accepts one `EnergySystemState` plus
required keyword-only decision facts. No parameter has a default value.

The only state-derived mappings are:

~~~text
state.battery.soc        -> context.soc
state.pv.actual_power_kw -> context.pv_power_kw
state.grid.grid_power_kw -> context.grid_power_kw
~~~

The caller must explicitly provide:

- `timestamp`;
- `battery_power_limit_kw`;
- `battery_energy_capacity_kwh`;
- `load_power_kw`;
- `electricity_price_cny_per_kwh`;
- `reserve_soc`; and
- `export_limit_kw`.

The assembler does not derive a power limit from battery charge or discharge
availability. It does not calculate load, normalize power direction, or supply
defaults.

## Units and Meaning

- `timestamp` is the caller-supplied, timezone-aware decision instant. Its
  exact object identity is retained by `DecisionContext`.
- SOC and reserve SOC are unitless fractions in `[0, 1]`.
- Power values and limits are in kW.
- Battery energy capacity is in kWh.
- Electricity price is a signed finite value in CNY per kWh.
- Positive grid power means import, negative means export, and zero means
  balanced exchange.

Assembly preserves these contracts without scaling or sign conversion.

## Validation

- `state` must be an `EnergySystemState`.
- Battery, PCS, PV, and grid components must all be present with their
  established types.
- Existing `DecisionContext` validation enforces SOC, timestamp, numeric range,
  finiteness, price, and constraint contracts.

## Statelessness

`DecisionContextAssembler` has empty slots and stores no state, policy, cache,
history, or runtime reference. Assembly reads its inputs and returns a new
immutable context without mutating any source object.

## Non-goals

- Extending `EnergySystemState`.
- EMS policy, optimization, or forecasting.
- Power balance or battery-limit calculation.
- Dispatch, commands, device control, or runtime execution.
- Persistence, telemetry, caches, or history.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
~~~
