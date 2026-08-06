# ADR-067 — Battery Simulation Actuation Contract

## Status

Accepted

## Context

Phase 6 already defines deterministic step identity/time and independent PV,
Load, and Tariff contracts. Before a Battery simulation model can be defined,
EOS needs an explicit seam between an already feasible decision and the power
request observed by that future model.

A feasible decision is not a Command and does not itself execute a simulated
battery. Likewise, an actuation artifact must not silently apply constraints,
derive power, advance state, or communicate with a device.

Phase 6 Architecture v2 additionally requires the actuation to retain the
exact feasible decision as provenance.

## Decision

Add frozen/slotted `BatterySimulationActuation` with exactly:

```text
source_feasible_decision: FeasibleDecisionIntent
battery_power_kw: float
```

No Battery model boundary or concrete implementation is introduced in this
task.

## Provenance decision

The actuation directly stores the caller-supplied feasible decision:

```text
actuation.source_feasible_decision is original_feasible_decision
```

Validation checks only its contract type. It does not copy, reconstruct,
serialize, normalize, or execute the decision.

## Power decision

Battery power is a signed finite raw kW value:

- positive means battery charging;
- negative means battery discharging;
- zero means idle.

There is no implicit scaling, conversion, clipping, saturation, SOC rule,
efficiency calculation, or equality requirement against the source decision.
The actuation power is an explicit caller fact.

## Ownership decision

The artifact owns no clock, simulation step, Battery state, model, Runtime,
Device, Command, cache, or history. TASK-070 may define a Battery model contract
that composes this exact actuation with explicit model input facts. Aggregate
step ownership remains reserved for TASK-072.

## Dependency decision

`simulator.battery` depends on the existing immutable
`FeasibleDecisionIntent` contract and local numeric validation. The dependency
does not reverse: Kernel Decision code has no Simulator dependency.

## Consequences

- Battery simulation input gains explicit decision provenance.
- Intent, feasible decision, simulation actuation, and Command remain distinct.
- Power direction and units are stable before Battery physics is introduced.
- Future Battery models can be replaced without changing the actuation seam.

## Rejected alternatives

### Store power without source provenance

Rejected because a simulation observation could not be traced to the exact
feasible decision that authorized it.

### Reconstruct a feasible decision inside the actuation

Rejected because value equality is not provenance and reconstruction breaks
identity.

### Derive power from the feasible decision

Rejected because TASK-069 defines transport semantics only and must not own a
conversion or decision-formation rule.

### Add Battery state or physics now

Rejected because Battery model/state transition contracts belong to later
Phase 6 tasks.

## Non-goals

- SOC/SOH, efficiency, degradation, voltage, current, temperature, or thermal
  calculation.
- Constraint evaluation, optimization, forecasting, or state transition.
- Runtime, Device, Command, Dispatch, PCS/BMS, protocol, or persistence.
- Aggregate Simulation State, Scenario, Step Input/Result, cache, or history.
