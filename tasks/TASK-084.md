# TASK-084 — Concrete Load Profile Simulation Model

Status: IN REVIEW

## Objective

Implement the first concrete Load component for EOS EMS Simulator 1.0. The
model converts one caller-supplied hourly Load profile fact into one immutable
`LoadSimulationResult`.

## Architecture

```text
DailySimulationScenarioInput.load_power_curve_kw[index]
        |
        | caller/future runner supplies the value
        v
LoadSimulationInput.demand_power_kw
        |
        v
LoadProfileSimulationModel
        |
        v
LoadSimulationResult.actual_power_kw
```

`LoadProfileSimulationModel` implements the frozen Phase 6
`LoadSimulationModelBoundary`. Phase 5–7 contracts remain unchanged.

## Model contract

- input: exact `LoadSimulationInput`;
- output: new immutable `LoadSimulationResult` referencing that exact input;
- output power: the input `demand_power_kw` value;
- unit: finite, non-negative raw kW;
- execution: stateless and deterministic;
- ownership: no profile, input, result, cache, or history retention.

The TASK-082 daily input remains the single owner of the 24-hour Load profile.
A future application runner will place each caller-supplied curve value in its
explicit hourly `LoadSimulationInput`. The model does not store a duplicate
profile or perform sequence lookup.

## Identity and determinism

For every successful call:

```text
result.simulation_input is original_input
result.simulation_input.step_identity is original_step_identity
```

Repeated calls with the same input produce equal observed values and distinct
immutable results. There is no input copy, reconstruction, normalization, or
retention.

## Non-goals

TASK-084 does not implement:

- user behavior or appliance models;
- stochastic Load generation;
- forecast or AI prediction;
- demand response or Load control;
- Runtime, Device, Command, Dispatch, or persistence;
- Optimization or EMS strategy;
- PV, Tariff, Battery, Grid, runner, CSV, or plotting behavior.

## Validation

- normal 24-hour caller profile;
- zero Load;
- negative and non-finite input rejection;
- exact input and step identity preservation;
- deterministic repeated evaluation;
- stateless empty-slotted implementation;
- exact caller model binding compatibility;
- public API and dependency isolation;
- full project quality checks.
