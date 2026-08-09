# TASK-083 — Concrete PV Profile Simulation Model

Status: IN REVIEW

## Objective

Implement the first concrete EOS EMS Simulator 1.0 component model. The model
converts one caller-supplied hourly PV profile fact into one immutable
`PVSimulationResult`.

## Architecture

```text
DailySimulationScenarioInput.pv_power_curve_kw[index]
        |
        | caller/future runner supplies the value
        v
PVSimulationInput.available_power_kw
        |
        v
PVProfileSimulationModel
        |
        v
PVSimulationResult.actual_power_kw
```

`PVProfileSimulationModel` implements the frozen Phase 6
`PVSimulationModelBoundary`. It does not modify that boundary or any Phase 5–7
contract.

## Model contract

- input: exact `PVSimulationInput`;
- output: new immutable `PVSimulationResult` referencing that exact input;
- output power: the input `available_power_kw` value;
- unit: finite, non-negative raw kW;
- execution: stateless and deterministic;
- ownership: no profile, input, result, cache, or history retention.

The model deliberately does not accept or store a second profile tuple. The
profile value already enters through `PVSimulationInput`, so duplicate profile
ownership would create two competing sources of truth. A future application
runner will map each exact TASK-082 curve value to its explicit hourly input.

## Identity and determinism

For every successful call:

```text
result.simulation_input is original_input
result.simulation_input.step_identity is original_step_identity
```

Repeated calls with the same input produce equal observed values while returning
independent immutable result artifacts. No copy, reconstruction, normalization,
or retention of the input occurs.

## Non-goals

TASK-083 does not implement:

- weather, irradiance, or temperature physics;
- forecast or profile generation;
- MPPT, inverter, PCS, or curtailment behavior;
- Runtime, Device, Command, Dispatch, or persistence;
- Optimization or EMS strategy;
- Load, Tariff, Battery, Grid, scenario-runner, CSV, or plotting behavior.

## Validation

- normal 24-hour caller profile;
- zero PV;
- negative and non-finite input rejection;
- exact input and step identity preservation;
- deterministic repeated evaluation;
- stateless empty-slotted implementation;
- exact caller model binding compatibility;
- public API and dependency isolation;
- full project quality checks.
