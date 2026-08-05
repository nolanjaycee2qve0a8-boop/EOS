# ADR-064 — PV Simulation Model Contract

## Status

Accepted

## Context

TASK-065 established explicit simulation step identity and time facts. Phase 6
next needs an independent photovoltaic component seam before aggregate
Simulation State, Scenario, Step Input, or Step Result can be defined.

Introducing PV physics now would mix the stable boundary with one calculation
model. Reading irradiance, inverter parameters, MPPT state, telemetry, or a
device would also violate the Simulation/Device separation.

## Decision

Add three public contracts in `simulator.pv`:

- frozen/slotted `PVSimulationInput`;
- frozen/slotted `PVSimulationResult`;
- abstract, stateless, empty-slotted `PVSimulationModelBoundary`.

No concrete production model is introduced.

## Input decision

Input directly stores an exact `SimulationStepIdentity` and one explicit
`available_power_kw` fact. Availability is non-negative finite raw kW supplied
by the caller.

It is not derived from irradiance, weather, efficiency, temperature, MPPT,
inverter rating, telemetry, or device access.

## Result decision

Result directly stores the exact `PVSimulationInput` and a non-negative finite
`actual_power_kw` observation. Actual power cannot exceed the explicit input
availability.

The upper bound is a representation invariant. The Result performs no PV
calculation, correction, curtailment decision, or explanation.

## Identity decision

```text
input.step_identity is original_step_identity
result.simulation_input is original_input
```

There is no copy, reconstruction, serialization, normalization of references,
or hidden source lookup.

## Boundary decision

The model boundary defines only:

```text
simulate(PVSimulationInput) -> PVSimulationResult
```

It owns no current state, parameters, cache, history, Runtime, Device,
Dispatcher, or Command. Future implementations are caller-supplied and remain
outside TASK-066.

## Dependency decision

The PV contract depends only on Phase 6 core identity/time and focused local
validation. No existing package depends on the PV boundary, and Simulator does
not depend on Runtime, Device, or execution layers.

## Consequences

- Phase 6 gains one stable immutable PV component seam.
- Aggregate simulation contracts can later reference exact PV artifacts.
- Different future PV models can remain replaceable.
- PV availability and actual generation units are explicit.
- Physics, MPPT, inverter, Device, and Runtime responsibilities remain outside
  the contract.

## Rejected alternatives

### Implement an irradiance-to-power formula

Rejected because TASK-066 is contract-only.

### Add inverter or MPPT fields

Rejected because they introduce implementation and device concerns.

### Read PV telemetry

Rejected because Simulation does not execute or observe a real device.

### Return a bare float

Rejected because the output would lose exact input provenance.

## Non-goals

- Concrete PV model, MPPT, inverter, irradiance, weather, or forecasting.
- Device, Runtime, Command, Dispatch, protocol, telemetry, or persistence.
- Aggregate simulation contracts, optimization, cache, or history.
