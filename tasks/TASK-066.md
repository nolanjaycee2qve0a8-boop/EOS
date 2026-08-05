# TASK-066 — PV Simulation Model Contract

Status: IN REVIEW

## Objective

Define the immutable and abstract Phase 6 photovoltaic simulation boundary.

TASK-066 represents explicit PV availability input and one simulated generation
observation. It introduces no photovoltaic physics, MPPT, inverter, device,
Runtime, Command, or model implementation.

## Architecture

```text
SimulationStepIdentity
        +
caller-supplied available_power_kw
        |
        v
PVSimulationInput
        |
        v
PVSimulationModelBoundary
        |
        v
PVSimulationResult(actual_power_kw)
```

## Input contract

`PVSimulationInput` is frozen and slotted with exactly:

- `step_identity: SimulationStepIdentity`;
- `available_power_kw: float`.

`available_power_kw` is a non-negative finite raw value in kW. It is an
explicit exogenous simulation fact, not irradiance conversion, an MPPT result,
an inverter rating, a forecast, or a device reading.

The exact step identity is preserved:

```text
simulation_input.step_identity is original_step_identity
```

## Result contract

`PVSimulationResult` is frozen and slotted with exactly:

- `simulation_input: PVSimulationInput`;
- `actual_power_kw: float`.

`actual_power_kw` is non-negative finite generated power in raw kW and cannot
exceed `simulation_input.available_power_kw`. This is an output-domain
invariant, not a calculation. The Result does not explain how a model obtained
the value.

The exact input identity is preserved:

```text
result.simulation_input is original_simulation_input
```

## Model boundary

`PVSimulationModelBoundary` is abstract, stateless, and empty-slotted:

```python
def simulate(
    self,
    simulation_input: PVSimulationInput,
) -> PVSimulationResult: ...
```

No concrete production model is introduced. Future physics or data-driven
models require separate TASKs and must preserve this contract.

## Dependency direction

```text
simulator.pv
    -> simulator.core
    -> simulator.validation
    -> Python standard library
```

There is no dependency on Kernel, Decision Formation, Runtime, Execution,
Dispatch, Device, PCS, BMS, protocols, optimization, or forecasting.

## Non-goals

- PV physics, irradiance conversion, temperature correction, or efficiency.
- MPPT, inverter, PCS, voltage, current, or device parameters.
- Forecasting, weather API, telemetry, or persistence.
- Aggregate Simulation State, Scenario, Step Result, or composition.
- Runtime, clock ownership, scheduler, Command, Dispatch, or Device execution.
- Optimization, cache, or history.

## Validation

Focused tests cover:

- exact step/input identity preservation;
- non-negative finite kW validation and bool rejection;
- actual power bounded by explicit availability;
- frozen/slotted field completeness and no `__dict__`;
- abstract empty-slotted model boundary;
- test-only exact-input model behavior;
- no concrete production model or forbidden dependency;
- public imports and full regression suite.
