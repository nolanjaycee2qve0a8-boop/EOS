# ADR-069 — Grid Simulation Model Contract

## Status

Accepted

## Context

Phase 6 has independent contracts for PV, Load, Tariff, and Battery. Before the
aggregate simulation contracts in TASK-072, EOS needs an independent Grid seam
that represents requested and actual exchange without prematurely owning
system power balance, Grid limits, device control, or infrastructure.

Treating Grid power as a Command or silently deriving it from other component
outputs would couple the component contract to future aggregate composition.
Embedding import/export limits would duplicate the existing Constraint layer.

## Decision

Add three public contracts in `simulator.grid`:

- frozen/slotted `GridSimulationInput`;
- frozen/slotted `GridSimulationResult`;
- abstract/stateless/empty-slotted `GridSimulationModelBoundary`.

No concrete production Grid model is introduced.

## Power decision

Input `requested_grid_power_kw` and Result `actual_grid_power_kw` are signed
finite raw values in kW:

- positive means Grid import;
- negative means Grid export;
- zero means balanced exchange.

Boolean and non-finite values are invalid. There is no hidden scaling, unit
conversion, sign inversion, clipping, or saturation.

Requested exchange is an explicit caller fact. Actual exchange is an explicit
model observation. The abstract artifact contract does not define the
calculation between them or require equality.

## Identity decision

```text
input.step_identity is original_step_identity
result.simulation_input is original_input
```

No copy, reconstruction, serialization, clock read, or hidden source lookup is
performed.

## Boundary decision

The model boundary defines only:

```text
simulate(GridSimulationInput) -> GridSimulationResult
```

It owns no Grid constraint, power-flow calculation, other component output,
Runtime, Device, Command, service, cache, or history.

## Consequences

- Grid import/export units and direction are explicit and stable.
- Requested and actual exchange are separate immutable facts.
- Future Grid implementations remain replaceable.
- Aggregate power balance remains reserved for TASK-072 or later explicit
  architecture work.
- Constraint, Runtime, and Device responsibilities remain isolated.

## Rejected alternatives

### Calculate Grid power from PV, Load, and Battery in the component contract

Rejected because that is aggregate composition, not an independent Grid model
contract.

### Enforce import/export limits

Rejected because physical feasibility belongs to the Constraint layer.

### Encode Zero Export behavior

Rejected because Zero Export is a policy/constraint capability, not a neutral
Grid observation contract.

### Treat requested exchange as a device Command

Rejected because Simulation input does not execute infrastructure.

### Add voltage, frequency, or fault behavior now

Rejected because TASK-071 freezes only the minimum stable Grid exchange seam.

## Non-goals

- Balance calculation, Grid limits, Zero Export, outage, islanding, fault, or
  power-quality physics.
- Constraint, policy, optimization, forecasting, Runtime, Device, Command, or
  Dispatch.
- Aggregate simulation composition, persistence, cache, or history.
