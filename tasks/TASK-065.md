# TASK-065 — Simulation Core Identity and Time Contracts

Status: IN REVIEW

## Objective

Establish the first Phase 6 immutable contract for explicit simulation step
identity and time facts.

TASK-065 does not create component models, aggregate simulation state, a step
orchestrator, Runtime behavior, device execution, Commands, or optimization.

## Architecture

```text
caller-supplied sequence
        +
caller-supplied duration
        +
caller-supplied timestamp or explicit None
        |
        v
SimulationStepIdentity
```

## Contract

`SimulationStepIdentity` is a frozen, slotted dataclass containing exactly:

- `sequence: int`;
- `duration_seconds: float`;
- `timestamp: datetime | None`.

`sequence` is a zero-based, non-negative step identity. Boolean values are not
integers for this contract.

`duration_seconds` is a finite raw duration in seconds and must be greater than
zero. Numeric input is normalized only to `float`; there is no unit conversion
or hidden scaling.

`timestamp` is either an explicit `None` or a timezone-aware `datetime`. The
exact caller-supplied datetime identity is preserved. The contract does not
read a wall clock or generate a timestamp.

## Identity

When a timestamp is supplied:

```text
step.timestamp is original_timestamp
```

The contract contains no mutable collections and no references to Runtime,
Device, Commands, component models, cache, or history.

## Dependency direction

```text
simulator.core
    -> Python standard library
    -> simulator.validation
```

Kernel, Decision Formation, Objective, Capability, Runtime, and Execution do
not depend on the simulation core.

## Non-goals

- PV, Load, Tariff, Battery, or Grid contracts or implementations.
- Simulation State, Scenario, aggregate Step Input, or Step Result.
- Model composition or automatic step progression.
- Runtime, clock ownership, scheduler, thread, queue, or async execution.
- Device, PCS, BMS, CAN, Modbus, MQTT, Command, or Dispatch.
- Constraint implementation, optimization, forecasting, persistence, cache,
  or history.

## Validation

Tests cover:

- valid sequence, duration, aware timestamp, and explicit absent timestamp;
- invalid types, negative sequence, non-positive/non-finite duration, and naive
  timestamp rejection;
- exact timestamp identity;
- frozen/slotted field completeness and absence of `__dict__`;
- dependency isolation and public import;
- full regression suite.
