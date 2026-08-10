# TASK-095 — Self Consumption EMS Strategy

## Objective

Implement the first concrete Phase 9 `EMSStrategyBoundary` implementation. The Strategy
uses existing immutable facts to produce an `EMSDecision` request only.

## Architecture

```text
EMSContext
    |
    v
SelfConsumptionStrategy
    |
    v
EMSDecision
    |
    v
existing Feasibility Boundary
```

## Decision rules

The Strategy reads the exact `DecisionContext` referenced by `EMSContext`:

- when PV power exceeds Load power, request charging by the raw surplus magnitude;
- when Load power exceeds PV power and SOC is greater than reserve SOC, request
  discharging by the raw deficit magnitude;
- otherwise, request idle with zero magnitude.

`requested_power_kw` is always a non-negative raw kW magnitude. Direction remains in the
semantic action: charge, discharge, or idle.

## Responsibility separation

The reserve-SOC comparison determines whether the Strategy requests discharge. It is not
physical SOC enforcement. The Strategy deliberately does not clip the request against
Battery power limits, predict the next SOC, enforce Grid limits, or execute an actuation.
Those responsibilities remain in Feasibility, handoff, and Simulator layers.

## Provenance and state

`SelfConsumptionStrategy` is empty-slotted and has no instance state, cache, or history.
Each result preserves:

- `decision.source_context is supplied_context`;
- `decision.source_strategy is SelfConsumptionStrategy.descriptor`.

The descriptor is an immutable class-level identity artifact. The Strategy does not copy
or reconstruct the supplied context.

## Non-goals

- no SOC limiting or state transition;
- no Battery power clipping or PCS limits;
- no Grid constraint or Zero Export enforcement;
- no TOU, MPC, Optimization, or Forecasting;
- no Simulator, Runtime, Device, PCS, or Command interaction;
- no modification to TASK-090–094 or Phase 5–8 contracts.

## Validation

- PV-surplus charge request;
- Load-deficit discharge request;
- reserve-SOC discharge prevention and balanced idle behavior;
- unclipped request behavior;
- exact context and strategy descriptor identity;
- statelessness, dependency isolation, full pytest, Ruff, mypy, and diff validation.
