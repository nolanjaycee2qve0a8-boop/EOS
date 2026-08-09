# TASK-086 — Grid Energy Balance Simulation Model

Status: IN REVIEW

## Objective

Implement the first concrete Grid energy-balance component for EOS EMS
Simulator 1.0. The model calculates one Grid exchange from completed same-step
PV, Load, and Battery simulation results.

## Corrected physical contract

The frozen signs are:

- Battery power greater than zero: charging;
- Battery power less than zero: discharging;
- Grid power greater than zero: import;
- Grid power less than zero: export;
- Grid power equal to zero: balanced.

The authoritative balance is:

```text
grid_power_kw = load_power_kw + battery_power_kw - pv_power_kw
```

Charging increases Grid import; discharging decreases Grid import. The earlier
draft expression `load - battery - pv` is rejected because it contradicts the
frozen Battery sign convention.

## Architecture

```text
exact PVSimulationResult
exact LoadSimulationResult
exact BatterySimulationResult
        |
        v
GridEnergyBalanceSimulationModel
        +
exact same-step GridSimulationInput
        |
        v
GridSimulationResult
```

`GridEnergyBalanceSimulationModel` is a frozen/slotted, per-step concrete
implementation of the existing Phase 6 `GridSimulationModelBoundary`. It stores
the exact three component result references and validates that they share one
exact `SimulationStepIdentity`. `simulate()` requires its Grid input to share
that same identity.

## Result contract

- `actual_grid_power_kw` is finite signed raw kW;
- the result references the exact supplied `GridSimulationInput`;
- the model preserves exact PV, Load, and Battery result references;
- `requested_grid_power_kw` is not substituted for the component-result
  balance and may differ from actual Grid exchange;
- no source result, input, or step is copied or reconstructed.

The model retains immutable evidence for one explicit step only. It owns no
evolving state, cache, history, or Runtime lifecycle.

## Execution scope

TASK-086 defines the concrete balance evaluation only. A future application
runner must supply completed same-step component results and coordinate when the
Grid model is invoked. This task does not change `SingleStepSimulationExecutor`,
scenario execution, binding contracts, or any Phase 5–7 API.

## Non-goals

TASK-086 does not implement Zero Export, import/export limits, EMS control,
strategy, PCS, inverter, Device, Command, Dispatch, Runtime, persistence,
Optimization, Forecast, or automatic component orchestration.

## Validation

- PV surplus/export;
- Battery charging increases import;
- Battery discharging decreases import;
- import, export, and zero balance;
- exact component-result and Grid-input identities;
- rejection of reconstructed equal step identities;
- deterministic repeated evaluation;
- frozen/slotted structure and dependency isolation;
- full project quality checks.
