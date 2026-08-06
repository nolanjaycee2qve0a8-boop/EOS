# TASK-069 — Battery Simulation Actuation Contract

Status: IN REVIEW

## Objective

Define the immutable Phase 6 artifact that carries one explicit battery power
actuation into a future battery simulation model while preserving the exact
feasible decision that authorized it.

TASK-069 is a contract only. It does not implement battery physics, state
transition, constraint evaluation, command generation, Runtime, or Device
execution.

## Architecture

```text
FeasibleDecisionIntent
        |
        v
BatterySimulationActuation
        |
        v
Future Battery Simulation Model (TASK-070)
```

## Contract

`BatterySimulationActuation` is frozen and slotted with exactly:

- `source_feasible_decision: FeasibleDecisionIntent`;
- `battery_power_kw: float`.

The source is the exact existing feasible decision object:

```text
actuation.source_feasible_decision is original_feasible_decision
```

There is no copy, reconstruction, serialization, or conversion of the source
decision.

## Battery power contract

`battery_power_kw` is a signed finite raw value in kW with no hidden scaling:

- positive: battery charging;
- negative: battery discharging;
- zero: idle.

Boolean and non-finite values are rejected. TASK-069 does not derive this
value from the source decision, clamp it, apply SOC or power limits, or advance
battery state. The caller supplies the explicit simulation actuation after
decision feasibility has already been established.

## Time and state ownership

The actuation does not own a simulation step, clock, state, history, or cache.
A future Battery model input or aggregate step contract may compose the exact
actuation with `SimulationStepIdentity` and immutable Battery state. TASK-069
does not introduce those later contracts early.

## Dependency direction

```text
simulator.battery
    -> kernel.decision.constraint
    -> simulator.validation
```

This direction reflects the frozen Phase 6 rule that Simulation consumes an
already feasible decision. Kernel and Decision contracts do not depend on the
Simulator.

## Non-goals

- Battery physics, SOC/SOH calculation, efficiency, degradation, or thermal
  modeling.
- Battery state, next-state transition, or concrete Battery model.
- Constraint evaluation, power clipping, optimization, or forecasting.
- Runtime, scheduler, clock, UUID, persistence, cache, or history.
- Command, Device, Dispatch, PCS, BMS, CAN, Modbus, or MQTT.
- Aggregate Simulation State, Scenario, Step Input, or Step Result.

## Validation

Focused tests cover exact feasible-decision identity, signed finite raw kW,
bool and non-finite rejection, frozen/slotted field completeness, source
immutability, public import, dependency direction, forbidden ownership, and
the full regression suite.
