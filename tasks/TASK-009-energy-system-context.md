# TASK-009 — Immutable Energy System Context Boundary

## Status

IN REVIEW

## Objective

Introduce one immutable aggregate input object for future EOS decision
processing. EnergySystemContext combines energy asset definitions, current
state observations, and one PowerFlow observation without calculating or
controlling anything.

## Scope

- An immutable EnergySystemContext with assets, states, and power_flow fields.
- Tuple-only asset and state collections with caller ordering preserved.
- Validation against the existing asset, state, and PowerFlow domain models.
- Asset-to-state presence matching by asset_id.
- Focused unit tests and a stable public import.

## Non-goals

- EMS policy, optimization, scheduling, or forecasting.
- Control, PCS operation, SOC calculation, or power calculation.
- Pricing, communication, telemetry, or persistence.
- Sorting, deduplication, type inference, or hidden normalization.
- Changes to the existing DecisionPipeline or runtime.

## Context Semantics

- `assets` contains only existing EnergyAsset models.
- `states` contains only BatteryState, PVState, or LoadState observations.
- `power_flow` is an already validated PowerFlow.
- Every asset_id in assets must occur in at least one state.
- Additional states are preserved because reverse matching was not specified.
- Caller tuple identity, order, and duplicate entries are preserved.

The repository currently has three concrete state models and no EnergyState
base class. EnergySystemContext therefore uses their explicit type union rather
than introducing a new state hierarchy.

## Acceptance Criteria

- EnergySystemContext is a frozen slotted dataclass with only the specified fields.
- Mutable lists are rejected for assets and states.
- Invalid tuple elements and invalid power_flow values raise TypeError.
- An asset without a matching state raises ValueError.
- Collections remain tuples and preserve caller order.
- Public imports support `from kernel.context import EnergySystemContext`.
- All existing tests and repository quality checks pass.

## Validation Commands

~~~bash
pytest
ruff check .
ruff format --check .
mypy .
pre-commit run --all-files
~~~

## Implementation Notes

EnergySystemContext validates and aggregates caller-owned domain values. It
does not calculate power, reconcile observations, select policies, or mutate
the objects it contains.
