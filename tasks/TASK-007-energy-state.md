# TASK-007 — Energy State Snapshot Foundation

## Status

IN REVIEW

## Objective

Introduce immutable operational state models while preserving the boundary
between physical asset definitions and current observations.

## Scope

- BatteryState with observed SOC and signed power.
- PVState and LoadState with observed non-negative power.
- EnergySnapshot containing ordered immutable state tuples.
- Focused validation, stable public imports, and deterministic unit tests.

## Non-goals

- SOC or SOH calculation and battery modeling.
- Telemetry acquisition, forecasting, optimization, or EMS policies.
- Controllers, device communication, or protocol adapters.
- Persistence, serialization, or DecisionPipeline integration changes.

## Architecture

EnergyAsset models describe physical capability. Energy state models describe
current observations for explicitly identified assets. EnergySnapshot groups
those observations into three ordered tuples without sorting or mutation.

The caller owns observation acquisition and ordering. A future adapter may
present EnergySnapshot data to DecisionPipeline through a separately designed
boundary; TASK-007 does not modify the existing pipeline contract.

## State Semantics

- Battery SOC is supplied directly and must be between zero and one.
- Negative battery power means charging.
- Positive battery power means discharging.
- PV and load power are non-negative observations.
- State models perform validation but no calculation.

## Acceptance Criteria

- All state models are frozen slotted dataclasses.
- Asset IDs are explicit, non-empty, and immutable.
- Numeric values are finite and satisfy their specified ranges.
- Invalid types raise TypeError and invalid values raise ValueError.
- EnergySnapshot accepts only tuples containing the correct state types.
- Tuple order and tuple object identity are preserved.
- Public imports expose all four state models.
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

Numeric inputs accept non-boolean integers or floats and normalize to floats.
Non-finite observations are rejected because they do not provide stable
comparable state. EnergySnapshot does not infer ordering, remove duplicates,
or look up matching asset definitions.
