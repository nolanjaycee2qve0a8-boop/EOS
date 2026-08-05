# ADR-065 — Load Simulation Model Contract

## Status

Accepted

## Context

TASK-065 established simulation identity/time and TASK-066 established the PV
component seam. Phase 6 next needs an independent load component contract
before aggregate simulation contracts can be defined.

Load prediction, user behavior, demand response, schedules, and device
telemetry are different responsibilities. Including them in the foundational
boundary would couple one future model to Runtime or external systems.

## Decision

Add three public contracts in `simulator.load`:

- frozen/slotted `LoadSimulationInput`;
- frozen/slotted `LoadSimulationResult`;
- abstract, stateless, empty-slotted `LoadSimulationModelBoundary`.

No concrete production model is introduced.

## Input decision

Input directly stores an exact `SimulationStepIdentity` and caller-supplied
non-negative finite raw `demand_power_kw` in kW.

Demand is an exogenous fact. The boundary does not forecast, generate, schedule,
interpret, or retrieve it from users or devices.

## Result decision

Result directly stores the exact Input and non-negative finite raw
`actual_power_kw`. Actual consumption cannot exceed explicit demand.

The upper bound is a representation invariant. It does not introduce load
curtailment, shedding, user behavior, or control logic.

## Identity decision

```text
input.step_identity is original_step_identity
result.simulation_input is original_input
```

No copy, reconstruction, serialization, normalization of references, or hidden
source lookup is permitted.

## Boundary decision

The model boundary defines only:

```text
simulate(LoadSimulationInput) -> LoadSimulationResult
```

It owns no current state, prediction model, user profile, schedule, Runtime,
Device, Command, cache, or history.

## Consequences

- Phase 6 gains a stable immutable load component seam.
- Future load implementations can remain replaceable.
- Aggregate contracts can preserve exact load artifacts.
- Forecasting, user behavior, Runtime, and Device responsibilities remain
  outside the contract.

## Rejected alternatives

### Generate demand inside the boundary

Rejected because the foundational contract must not hide prediction or user
behavior logic.

### Read a smart meter or device

Rejected because Simulation is not Device execution or telemetry ingestion.

### Add schedules or demand-response commands

Rejected because they are control and orchestration concerns.

### Return a bare float

Rejected because output provenance would be lost.

## Non-goals

- Prediction, profile generation, user behavior, demand response, or control.
- Runtime, Device, Command, Dispatch, protocols, telemetry, or persistence.
- Aggregate simulation contracts, optimization, cache, or history.
