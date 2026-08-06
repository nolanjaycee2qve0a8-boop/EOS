# TASK-070 — Battery Simulation Model Contract

Status: IN REVIEW

## Objective

Define the immutable artifacts and abstract extension boundary for one
deterministic Battery simulation state transition.

TASK-070 composes the exact simulation step, source Battery state, and
TASK-069 actuation. It does not implement Battery physics, SOC calculation,
efficiency, degradation, constraints, Runtime, or Device execution.

## Architecture

```text
SimulationStepIdentity
        +
BatterySimulationState
        +
BatterySimulationActuation(source feasible decision)
        |
        v
BatterySimulationInput
        |
        v
BatterySimulationModelBoundary
        |
        v
BatterySimulationResult(next state, actual power)
```

## State contract

`BatterySimulationState` is frozen and slotted with exactly:

- `soc: float`.

SOC is a finite raw unitless fraction in the closed range `[0, 1]`. There is
no percentage scaling, hidden conversion, calculation method, mutable history,
or device status.

## Input contract

`BatterySimulationInput` is frozen and slotted with exactly:

- `step_identity: SimulationStepIdentity`;
- `source_state: BatterySimulationState`;
- `actuation: BatterySimulationActuation`.

All three references preserve exact caller identity:

```text
input.step_identity is original_step
input.source_state is original_source_state
input.actuation is original_actuation
input.actuation.source_feasible_decision is original_feasible_decision
```

## Result contract

`BatterySimulationResult` is frozen and slotted with exactly:

- `simulation_input: BatterySimulationInput`;
- `next_state: BatterySimulationState`;
- `actual_power_kw: float`.

The input and next-state references are preserved exactly. An unchanged step
may reuse the source-state identity; a transition may supply a distinct new
immutable state. The result never mutates the source state.

`actual_power_kw` is signed finite raw kW:

- positive: battery charging;
- negative: battery discharging;
- zero: idle.

The contract does not calculate, clamp, or require equality between requested
actuation and actual power. Such behavior belongs to a future concrete model.

## Model boundary

`BatterySimulationModelBoundary` is abstract, stateless, and empty-slotted:

```python
def simulate(
    self,
    simulation_input: BatterySimulationInput,
) -> BatterySimulationResult: ...
```

No concrete production Battery model is introduced.

## Dependency direction

```text
simulator.battery
    -> simulator.core
    -> simulator.validation
    -> kernel.decision.constraint (actuation provenance only)
```

Kernel, Decision, Runtime, and Device layers do not depend on Simulator.

## Non-goals

- SOC transition calculation, capacity integration, efficiency, loss,
  degradation, SOH, voltage, current, temperature, or electrochemistry.
- Power clipping, constraint evaluation, optimization, or forecasting.
- Runtime, scheduler, clock ownership, UUID, persistence, cache, or history.
- Command, Device, Dispatch, PCS, BMS, CAN, Modbus, or MQTT.
- Grid balance or aggregate Simulation State/Scenario/Step contracts.

## Validation

Focused tests cover SOC units/range, exact step/state/actuation/input/next-state
identities, unchanged and new-state transitions, signed power, frozen/slotted
field completeness, abstract boundary behavior, dependency isolation, public
imports, and the full regression suite.
