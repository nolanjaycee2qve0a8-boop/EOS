# TASK-104 — Forecast-Aware Peak Shaving Strategy

## Objective

Allow the existing `PeakShavingStrategy` to consume an optional,
caller-supplied `ForecastHorizon` without adding future predictions to
`EMSContext` or changing the base `EMSStrategyBoundary` contract.

## Architecture

```text
EMSContext (current facts) + optional ForecastHorizon (future facts)
    |
    v
PeakShavingStrategy.evaluate(context, forecast_horizon=...)
    |
    v
EMSDecision
```

## Deterministic behavior

Calling `evaluate(context)` without a forecast retains the TASK-099 behavior:
current Load above `demand_limit_kw` requests `discharge` for the raw-kW
excess; otherwise it requests `idle`.

When a forecast is supplied, a current Load excess still takes precedence. If
current Load is not above the limit, the Strategy scans the caller-ordered
horizon and uses the first future point above the demand limit. It requests
`discharge` with that point's raw-kW excess. An empty or non-exceeding horizon
requests `idle`.

This is a fixed deterministic look-ahead rule. It does not plan, score,
schedule, optimize, or solve over the horizon.

## Provenance and separation

The returned `EMSDecision` preserves exact `EMSContext` and
`PeakShavingStrategy.descriptor` identity. The horizon and each forecast point
remain caller-owned: they are read by reference and are neither retained,
copied, reconstructed, nor mutated by the Strategy.

`EMSContext`, `EMSDecision`, `DecisionProvenance`, feasibility, actuation,
coordinator, and Simulator contracts are unchanged.

## Non-goals

- no forecast generation, service, persistence, or cache;
- no MPC, optimization, ranking, scoring, or scheduling;
- no SOC handling, Battery power limit, Grid limit, clipping, or feasibility;
- no Simulator, runtime, device, command, or actuation work.

## Validation

- existing no-forecast peak-shaving behavior;
- current-load precedence and future Load peak detection;
- empty and non-exceeding forecast behavior;
- exact context, descriptor, horizon tuple, and point identity preservation;
- frozen/slotted state and dependency isolation;
- full pytest, Ruff, mypy, and diff validation.
