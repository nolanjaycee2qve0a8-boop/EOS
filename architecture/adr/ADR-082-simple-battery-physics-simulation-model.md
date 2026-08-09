# ADR-082: Simple Battery Physics Simulation Model

## Status

Accepted

## Context

TASK-082 supplies immutable Battery capacity, power limits, efficiencies, reserve
SOC, and initial SOC. Phase 6 already defines immutable Battery input, actuation,
state, result, and model contracts. EOS now needs a concrete deterministic state
transition without changing those frozen contracts or introducing Runtime or
device behavior.

The model must distinguish requested actuation from physically realized power.
It must also define which side of the efficiency calculation the signed power
represents and prevent an explicit step from producing SOC outside the modeled
bounds.

## Decision

Add frozen/slotted `ems_simulator.SimpleBatteryPhysicsModel`, configured with the
exact caller-supplied `BatteryParameters`.

The signed `battery_power_kw` and result `actual_power_kw` represent power at the
simulation system boundary:

- positive charging consumes boundary energy; stored energy is multiplied by
  `charge_efficiency`;
- negative discharging supplies boundary energy; removed stored energy is
  divided by `discharge_efficiency`.

Actual power is the requested magnitude clipped by the applicable configured
power limit and SOC energy boundary. Charging cannot exceed SOC `1.0`.
Discharging cannot move SOC below `reserve_soc`.

If the source SOC is already below reserve, the model blocks further discharge
without inventing energy or normalizing the state. A zero transition preserves
the exact source-state identity; a nonzero transition creates a new immutable
state.

## Consequences

- The Simulator can now calculate deterministic SOC transitions from explicit
  Battery actuation and duration.
- `actual_power_kw` may differ from requested power because physical limits are
  modeled explicitly.
- Result evidence retains the exact Battery input and its complete decision
  provenance.
- Immutable parameters may be stored by the model, but no evolving state,
  current step, cache, or history is retained.
- This simple model assumes constant capacity and efficiency for each step.

## Boundary relationship

The decision/constraint layers express and authorize intent. Battery simulation
realizes that actuation and protects its own modeled state invariants. It does
not infer an EMS objective, produce a new decision, or communicate with a
Battery device.

## Rejected alternatives

### Mutate the source Battery state

Rejected because Phase 6 state is immutable and exact provenance must remain
available.

### Store current SOC inside the model

Rejected because step state is explicit input and hidden retention would break
determinism and Phase 7 progression ownership.

### Ignore efficiency or apply one formula to both directions

Rejected because charging stores less than boundary input energy while
discharging removes more stored energy than boundary output energy.

### Normalize a below-reserve source SOC upward

Rejected because that would create stored energy without a charging actuation.

### Add SOH, thermal, cell, BMS, PCS, Runtime, or strategy behavior

Rejected as outside the minimal Simulator 1.0 Battery physics scope.
