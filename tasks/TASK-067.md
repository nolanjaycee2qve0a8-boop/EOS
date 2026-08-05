# TASK-067 — Load Simulation Model Contract

Status: IN REVIEW

## Objective

Define the immutable and abstract Phase 6 electrical load simulation boundary.

TASK-067 represents explicit load demand input and one simulated consumption
observation. It introduces no load prediction, user behavior model,
demand-response logic, Runtime, Device, Command, or concrete model.

## Architecture

```text
SimulationStepIdentity
        +
caller-supplied demand_power_kw
        |
        v
LoadSimulationInput
        |
        v
LoadSimulationModelBoundary
        |
        v
LoadSimulationResult(actual_power_kw)
```

## Input contract

`LoadSimulationInput` is frozen and slotted with exactly:

- `step_identity: SimulationStepIdentity`;
- `demand_power_kw: float`.

`demand_power_kw` is a non-negative finite raw value in kW supplied by the
caller. It is an exogenous simulation fact, not a forecast, user behavior
calculation, demand-response instruction, schedule, or device observation.

Identity is preserved:

```text
simulation_input.step_identity is original_step_identity
```

## Result contract

`LoadSimulationResult` is frozen and slotted with exactly:

- `simulation_input: LoadSimulationInput`;
- `actual_power_kw: float`.

`actual_power_kw` is non-negative finite consumed power in raw kW and cannot
exceed the explicit input demand. This is a representation invariant, not a
load model or curtailment algorithm.

```text
result.simulation_input is original_simulation_input
```

## Model boundary

`LoadSimulationModelBoundary` is abstract, stateless, and empty-slotted:

```python
def simulate(
    self,
    simulation_input: LoadSimulationInput,
) -> LoadSimulationResult: ...
```

No concrete production model is introduced.

## Dependency direction

```text
simulator.load
    -> simulator.core
    -> simulator.validation
    -> Python standard library
```

There is no dependency on Kernel, Decision Formation, Runtime, Device,
Command, Dispatch, optimization, forecasting, or user behavior systems.

## Non-goals

- Load prediction, profile generation, or user behavior modeling.
- Demand response, scheduling, shedding, or control.
- Device telemetry, metering, protocols, or communication.
- Aggregate Simulation State, Scenario, Step Result, or composition.
- Runtime, clock ownership, scheduler, Command, Dispatch, or Device execution.
- Optimization, persistence, cache, or history.

## Validation

Focused tests cover exact identity, type/range validation, frozen/slotted field
contracts, abstract boundary behavior, dependency isolation, no concrete model,
public imports, and the full regression suite.
