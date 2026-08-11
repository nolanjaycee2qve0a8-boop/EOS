# TASK-105 — MPC Strategy Contract

## Objective

Introduce a contract-only extension seam for a future Model Predictive Control
(MPC) Strategy. This task creates no solver, objective function, planning
algorithm, or physical control behavior.

## Architecture

```text
EMSContext (current facts) + ForecastHorizon (future facts) + MPCConfiguration
    |
    v
MPCStrategyInput
    |
    v
MPCStrategyBoundary
    |
    v
EMSDecision
    |
    v
existing Feasibility -> Actuation -> Simulator
```

## Contracts

`MPCConfiguration` is frozen and slotted. It declares only the required count
of forecast points and an explicit positive control-step duration in raw
seconds. It does not store objective weights, a solver, predicted state, cache,
or history.

`MPCStrategyInput` is frozen and slotted. It preserves the exact caller-owned
references to `EMSContext`, `ForecastHorizon`, and `MPCConfiguration`. It
requires that the horizon point count equals the declared configuration count;
it does not copy, merge, sort, or reconstruct forecast facts.

`MPCStrategyBoundary` is an abstract, empty-slotted seam accepting one
`MPCStrategyInput` and returning one existing `EMSDecision`. A conforming
implementation must preserve
`decision.source_context is strategy_input.context` and preserve its exact
existing strategy descriptor identity.

The dedicated input keeps future facts explicit without changing the general
`EMSStrategyBoundary(context) -> EMSDecision` ABI or `StrategyCoordinator`.
Output and provenance remain compatible through the existing `EMSDecision`
contract.

## Responsibility separation

- MPC is an advanced Strategy extension point; it can request an
  `EMSDecision`, but cannot bypass that artifact.
- `ForecastHorizon` is caller-supplied future information, not part of current
  `EMSContext` and not a forecast-generation service.
- Feasibility remains the downstream physical-permission layer.
- Actuation remains the downstream EMS-to-Simulator handoff layer.

## Non-goals

- no LP, QP, MILP, nonlinear solver, objective weighting, or optimization;
- no Battery state prediction, SOC handling, clipping, or feasibility logic;
- no forecast generation, persistence, cache, or history;
- no Simulator, runtime, device, PCS, command, dispatch, or Coordinator change;
- no modification to existing Context, Decision, Forecast, Feasibility,
  Actuation, Simulator, or Phase 5–8 contracts.

## Validation

- immutable/slotted configuration and input contracts;
- exact Context, Horizon, Configuration, tuple, and point identity;
- input type and horizon-count validation;
- abstract/stateless boundary and a minimal test implementation;
- exact returned `EMSDecision` provenance and descriptor identity;
- static dependency isolation; full pytest, Ruff, mypy, and diff validation.
