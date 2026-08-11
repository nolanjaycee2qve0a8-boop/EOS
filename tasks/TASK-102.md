# TASK-102 — Forecast Horizon Interface

## Objective

Introduce immutable, caller-supplied future-information contracts without
placing predictions in `EMSContext` or changing any Strategy or simulation
behavior.

## Architecture

```text
current measured facts                 caller-supplied future predictions
EMSContext                             ForecastHorizon
    |                                      |
    +----------- future Strategy input ----+
```

`EMSContext` remains the snapshot of current measured facts. A future strategy
may receive a separate `ForecastHorizon`, but TASK-102 does not alter the
existing strategy boundary.

## Contracts

`ForecastPoint` contains one timezone-aware future timestamp, finite
non-negative raw PV and Load kW predictions, and an optional signed finite raw
electricity price in CNY per kWh. It produces no prediction.

`ForecastHorizon` retains the exact caller-supplied tuple and exact point
references. Points must be strictly increasing by timestamp. An empty horizon
is valid. The caller declares these timestamps as future information; the
contract has no clock dependency. The collection neither sorts, deduplicates,
creates, selects, nor modifies predictions.

## Non-goals

- no AI, weather, cloud, telemetry, or prediction service;
- no optimization, MPC, forecast-driven Strategy, or Strategy API change;
- no feasibility, actuation, simulator, runtime, device, or command work;
- no modification to `EMSContext` or Phase 5–9 contracts.

## Validation

- frozen/slotted point and horizon contracts;
- optional price and finite power/price validation;
- exact caller tuple, point, and timestamp identity preservation;
- empty horizon and ordering behavior;
- static isolation from `EMSContext` and prediction-service dependencies;
- full pytest, Ruff, mypy, and diff validation.
