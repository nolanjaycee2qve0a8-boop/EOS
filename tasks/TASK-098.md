# TASK-098 — Time Of Use Strategy

## Objective

Add a concrete Phase 9 `TOUStrategy` that produces one `EMSDecision` request from the
current tariff fact. The Strategy is independent of the prior capability-layer TOU
implementation and performs no physical feasibility or execution work.

## Architecture

```text
EMSContext
    |
    v
TOUStrategy + caller-supplied TOUStrategyConfiguration
    |
    v
EMSDecision
```

## Configuration contract

`TOUStrategyConfiguration` is frozen and slotted. It contains:

- low and high price thresholds as signed, finite, unscaled CNY per kWh values;
- charge and discharge request powers as finite positive raw kW magnitudes.

The low threshold must be strictly lower than the high threshold, leaving an explicit
normal-price interval. Configuration is supplied by the caller and held by exact identity;
it has no price-service lookup, cache, history, or runtime behavior.

## V1 behavior

- price at or below the low threshold requests `charge`;
- price at or above the high threshold requests `discharge`;
- price strictly between the thresholds requests `idle`.

`requested_power_kw` remains a non-negative magnitude. Direction remains semantic in the
`DecisionIntent` action rather than a signed device command.

## Responsibility separation

TOU only forms a business request. It does not protect SOC, apply Battery power limits,
clip a request, calculate Grid feasibility, coordinate Strategies, execute physical models,
or issue Commands. Those concerns remain in later feasibility and handoff boundaries.

## Non-goals

- no SOC protection, Battery power limit, or clipping;
- no Optimization, Forecasting, MPC, coordinator, or external price service;
- no Simulator, Runtime, Device, PCS, or Command interaction;
- no modification to TASK-090–097 or Phase 5–8 contracts.

## Validation

- low/high/normal tariff outcomes and inclusive thresholds;
- exact context and immutable configuration identity;
- frozen/slotted configuration-bearing Strategy without runtime state;
- invalid configuration rejection and dependency isolation;
- full pytest, Ruff, mypy, and diff validation.
