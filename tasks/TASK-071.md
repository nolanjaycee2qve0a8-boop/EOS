# TASK-071 — Grid Simulation Model Contract

Status: IN REVIEW

## Objective

Define the immutable and abstract Phase 6 Grid simulation boundary.

TASK-071 represents one explicit requested Grid exchange and one simulated
actual Grid exchange for an exact simulation step. It does not calculate power
balance, enforce Grid constraints, implement Zero Export, execute a Command, or
access Runtime or Device infrastructure.

## Architecture

```text
SimulationStepIdentity
        +
caller-supplied requested Grid exchange
        |
        v
GridSimulationInput
        |
        v
GridSimulationModelBoundary
        |
        v
GridSimulationResult(actual Grid exchange)
```

## Input contract

`GridSimulationInput` is frozen and slotted with exactly:

- `step_identity: SimulationStepIdentity`;
- `requested_grid_power_kw: float`.

Requested power is a signed finite raw value in kW:

- positive: import from the Grid;
- negative: export to the Grid;
- zero: balanced exchange.

It is an explicit caller-supplied simulation fact, not a power-flow
calculation, device setpoint, Grid constraint, or Command.

```text
simulation_input.step_identity is original_step_identity
```

## Result contract

`GridSimulationResult` is frozen and slotted with exactly:

- `simulation_input: GridSimulationInput`;
- `actual_grid_power_kw: float`.

Actual power uses the same signed finite raw kW convention. The result
preserves the exact Input identity:

```text
result.simulation_input is original_simulation_input
```

The contract does not require actual power to equal requested power. It does
not calculate, clip, constrain, or explain either value.

## Model boundary

`GridSimulationModelBoundary` is abstract, stateless, and empty-slotted:

```python
def simulate(
    self,
    simulation_input: GridSimulationInput,
) -> GridSimulationResult: ...
```

No concrete production Grid model is introduced.

## Dependency direction

```text
simulator.grid
    -> simulator.core
    -> simulator.validation
    -> Python standard library
```

The contract has no dependency on Decision, Capability, Constraint, Runtime,
Device, Command, Dispatch, or external Grid services.

## Non-goals

- Power-balance calculation or automatic derivation from PV, Load, or Battery.
- Import/export limit enforcement, Zero Export, islanding, outage, or fault
  behavior.
- Voltage, frequency, reactive power, phase, or power-quality simulation.
- Grid Constraint, TOU, pricing strategy, optimization, or forecasting.
- Runtime, Device, Command, Dispatch, PCS, meter, CAN, Modbus, or MQTT.
- Aggregate Simulation State, Scenario, Step Input/Result, cache, or history.

## Validation

Focused tests cover signed power direction and units, bool and non-finite
rejection, exact step/input identities, requested/actual separation,
frozen/slotted field completeness, abstract boundary behavior, dependency
isolation, public imports, and the full regression suite.
