# ADR-068 — Battery Simulation Model Contract

## Status

Accepted

## Context

TASK-069 separated an already feasible decision from explicit Battery
simulation actuation. Phase 6 next needs a replaceable Battery model seam that
relates an exact step, immutable source state, and exact actuation to an
immutable next-state observation.

Embedding SOC calculation, efficiency, degradation, or device behavior into
the contract would freeze one Battery physics implementation and blur
Simulation with Runtime or Device execution.

## Decision

Extend `simulator.battery` with:

- frozen/slotted `BatterySimulationState`;
- frozen/slotted `BatterySimulationInput`;
- frozen/slotted `BatterySimulationResult`;
- abstract/stateless/empty-slotted `BatterySimulationModelBoundary`.

No concrete production model is introduced.

## State decision

The first state contract contains only `soc`, represented as a finite raw
unitless fraction in `[0, 1]`. It has no behavior, mutable collection, history,
device status, or hidden percentage scaling.

## Transition decision

Input preserves exact references to:

```text
SimulationStepIdentity
BatterySimulationState as source_state
BatterySimulationActuation
```

Result preserves exact references to its Input and caller-supplied immutable
next state. The source and next state may be the same object for no change, or
different objects for a transition. Neither is mutated.

The abstract contract does not calculate the transition. A future concrete
model may do so without changing these artifacts.

## Power decision

Result `actual_power_kw` is signed finite raw kW and uses the same convention
as TASK-069 actuation:

- positive means charging;
- negative means discharging;
- zero means idle.

The contract does not enforce equality with requested actuation, calculate
losses, or apply limits. These would be concrete model or constraint behavior.

## Provenance decision

```text
input.step_identity is original_step
input.source_state is original_source_state
input.actuation is original_actuation
result.simulation_input is original_input
result.next_state is caller_supplied_next_state
```

Because actuation already preserves its exact feasible decision, the complete
provenance chain remains observable without copy or reconstruction.

## Consequences

- Battery state transition has a deterministic, immutable extension seam.
- Source and next state are explicitly distinct lifecycle roles.
- Battery power units and direction remain stable.
- Physics implementations remain replaceable and testable.
- Runtime, Device, and Command remain outside Simulation.

## Rejected alternatives

### Mutate source state in place

Rejected because deterministic replay requires immutable state transitions.

### Calculate SOC in the artifact

Rejected because artifacts validate facts; concrete models calculate behavior.

### Require next state to be a distinct object

Rejected because an idle or no-change transition may legitimately preserve
the exact state identity.

### Force actual power to equal requested actuation

Rejected because the abstract result must allow future physics to represent
losses or other explicit effects without hidden correction in the artifact.

### Add electrical or thermal detail now

Rejected because TASK-070 freezes the minimum stable model seam only.

## Non-goals

- Concrete Battery physics, SOC/SOH, efficiency, degradation, thermal, voltage,
  current, capacity integration, or electrochemistry.
- Constraint, optimization, forecast, Runtime, Device, Command, or Dispatch.
- Aggregate simulation composition, persistence, cache, or history.
