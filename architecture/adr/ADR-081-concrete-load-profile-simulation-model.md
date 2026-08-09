# ADR-081: Concrete Load Profile Simulation Model

## Status

Accepted

## Context

TASK-082 introduced a caller-owned 24-hour Load curve, and TASK-083 established
the first concrete profile-component pattern for PV. EOS now needs a concrete
Load component that can participate in the frozen Phase 7 execution path without
changing the Phase 6 Load contract.

`LoadSimulationInput.demand_power_kw` already contains one explicit finite,
non-negative raw-kW profile fact. Storing the complete profile again inside the
model would duplicate ownership and introduce hidden sequence lookup.

## Decision

Add `ems_simulator.LoadProfileSimulationModel` as an empty-slotted concrete
implementation of `LoadSimulationModelBoundary`.

Each evaluation returns:

```text
LoadSimulationResult(
    simulation_input=the exact original input,
    actual_power_kw=simulation_input.demand_power_kw,
)
```

The caller or future application runner remains responsible for selecting the
TASK-082 Load curve value and constructing the existing Phase 6 input. The model
does not own, copy, or reconstruct the curve.

## Consequences

- The concrete Load model can use existing Phase 7 binding and execution.
- Equal explicit inputs produce equal Load observations deterministically.
- Result provenance retains exact input and step identities.
- The model owns no mutable state, cache, history, clock, or lookup rules.
- Actual Load equals caller demand in this demo; richer behavior requires a
  future explicit implementation.

## Rejected alternatives

### Store the 24-hour Load profile in the model

Rejected because TASK-082 already owns the profile and duplicate ownership would
create competing facts.

### Add the model to `simulator.load`

Rejected because Phase 6 contracts are frozen. Application behavior belongs to
`ems_simulator`.

### Generate Load from behavior, appliances, randomness, forecast, or AI

Rejected because TASK-084 is a deterministic profile adapter, not a Load
generation or prediction task.

### Add strategy, optimization, Runtime, or device control

Rejected because these responsibilities do not belong to the Load component.
