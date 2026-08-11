# TASK-103 — Forecast-Aware TOU Strategy

## Objective

Allow the existing concrete `TOUStrategy` to consume an optional,
caller-supplied `ForecastHorizon` without placing future predictions in
`EMSContext` or changing the base strategy boundary.

## Contract

```text
EMSContext (current facts) + optional ForecastHorizon (future facts)
    |
    v
TOUStrategy.evaluate(context, forecast_horizon=...)
    |
    v
EMSDecision
```

Calling `evaluate(context)` without a forecast remains the exact TASK-098
current-price-only behavior. The `ForecastHorizon` is an optional keyword-only
argument and is not stored by the frozen/slotted Strategy.

## Deterministic V1 look-ahead

Current low and high prices continue to take precedence. For a current normal
price only:

- a horizon with one-or-more high-price predictions and no low-price prediction
  requests `charge`;
- a horizon with one-or-more low-price predictions and no high-price prediction
  requests `discharge`;
- an empty, price-unavailable, or mixed high/low horizon requests `idle`.

The rule uses existing configured request magnitudes. It is a fixed threshold
rule, not an optimization, ranking, scheduling, or MPC algorithm.

## Provenance and separation

The returned `EMSDecision` continues to preserve the exact current
`EMSContext` and exact `TOUStrategy.descriptor` identity. `EMSDecision` and
`DecisionProvenance` are unchanged: the optional forecast remains caller-owned
input, is read by exact reference, and is neither copied nor retained as
mutable Strategy state. It is intentionally not added to decision provenance,
which would change the existing decision contract.

## Non-goals

- no AI or external forecast service;
- no MPC, solver, optimization, or coordinator change;
- no SOC/power/Grid feasibility logic;
- no simulator, runtime, device, command, or actuation change.

## Validation

- current-price-only compatibility;
- high, low, empty, unavailable, and mixed forecast behavior;
- exact context, descriptor, horizon tuple, and point identity preservation;
- frozen/slotted Strategy state and dependency isolation;
- full pytest, Ruff, mypy, and diff validation.
