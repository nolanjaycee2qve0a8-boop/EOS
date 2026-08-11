# TASK-099 — Peak Shaving Strategy

## Objective

Add a concrete Phase 9 `PeakShavingStrategy` that requests Battery discharge when the
current Load exceeds a caller-supplied demand limit. The result is only an `EMSDecision`
request; it is not an approved physical action or actuation.

## Architecture

```text
EMSContext
    |
    v
PeakShavingStrategy + PeakShavingConfiguration
    |
    v
EMSDecision
```

## Configuration contract

`PeakShavingConfiguration` is frozen and slotted with one field:

- `demand_limit_kw`: finite non-negative raw kW Load limit.

The limit is caller supplied by exact identity. It is a business demand target, not a
Battery power limit and not a Device capability fact.

## V1 behavior

- when `load_power_kw > demand_limit_kw`, request `discharge` with magnitude
  `load_power_kw - demand_limit_kw`;
- otherwise request `idle` with zero magnitude.

The exact supplied `EMSContext` is preserved by the resulting `EMSDecision`; the fixed
immutable strategy descriptor is also preserved.

## Responsibility separation

Peak Shaving does not read SOC, Battery power availability, or Grid constraints. It does
not clip the requested magnitude, decide physical feasibility, create actuation, or run an
execution model. Those responsibilities remain downstream.

## Non-goals

- no SOC check, Battery power limit, clipping, or feasibility logic;
- no Simulator interaction or actuation;
- no Optimization, Forecasting, MPC, coordinator, Runtime, Device, PCS, or Command;
- no modification to `EMSDecision`, feasibility contracts, or Simulator contracts.

## Validation

- above-limit discharge and at/below-limit idle behavior;
- exact Context, descriptor, and configuration identity;
- frozen/slotted configuration-bearing Strategy without runtime state;
- invalid configuration rejection and dependency isolation;
- full pytest, Ruff, mypy, and diff validation.
