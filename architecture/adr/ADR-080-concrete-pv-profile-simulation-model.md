# ADR-080: Concrete PV Profile Simulation Model

## Status

Accepted

## Context

TASK-082 introduced one immutable 24-hour data input, including the caller's PV
power curve. EOS now needs its first concrete application model while keeping
the Phase 6 component contract and Phase 7 execution architecture frozen.

`PVSimulationInput.available_power_kw` already represents the explicit,
non-negative finite raw-kW value for one step. A concrete profile model could
either consume this fact directly or store another profile and select from it by
sequence. The latter would duplicate ownership and couple the model to a fixed
scenario length and lookup policy.

## Decision

Add `ems_simulator.PVProfileSimulationModel` as an empty-slotted concrete
implementation of `PVSimulationModelBoundary`.

For each exact `PVSimulationInput`, it returns:

```text
PVSimulationResult(
    simulation_input=the exact original input,
    actual_power_kw=simulation_input.available_power_kw,
)
```

The caller or a future application runner remains responsible for selecting the
appropriate TASK-082 profile value and constructing the existing Phase 6 input.
The model neither owns nor reconstructs the curve.

## Consequences

- The first concrete component can participate in existing Phase 7 model
  binding and execution without contract changes.
- Equal explicit inputs produce equal power observations deterministically.
- Input and step provenance remain exact and inspectable.
- The implementation has no mutable state, cache, history, or hidden lookup.
- PV generation equals caller availability in this simple demo model; richer PV
  physics or curtailment requires a future explicit implementation.

## Rejected alternatives

### Store the 24-hour profile inside the model

Rejected because the profile already belongs to the caller's TASK-082 scenario
input. Storing it again would duplicate facts and introduce sequence lookup.

### Add the concrete model to `simulator.pv`

Rejected because Phase 6 contracts are frozen. Concrete demo behavior belongs
to the `ems_simulator` application layer.

### Calculate PV from weather or irradiance

Rejected because TASK-083 is a deterministic profile adapter, not a PV physics
or forecasting task.

### Add inverter, MPPT, PCS, strategy, or optimization behavior

Rejected because those responsibilities are outside the PV profile model and
outside TASK-083.
