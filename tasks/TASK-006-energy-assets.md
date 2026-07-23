# TASK-006 — Energy Asset Domain Foundation

## Status

IN REVIEW

## Objective

Introduce the first EOS energy domain models for generic energy assets,
batteries, photovoltaic generation, and electrical loads.

## Scope

- An immutable EnergyAsset base definition with explicit identity and name.
- Immutable BatteryAsset rated capacity and charge/discharge limits.
- Immutable PVAsset and LoadAsset rated power definitions.
- Focused validation, stable public imports, and deterministic unit tests.

## Non-goals

- EMS algorithms, optimization, scheduling, or forecasting.
- SOC, SOH, electrochemical behavior, or battery calculations.
- BMS, PCS, MPPT, or controller implementation.
- Telemetry, device communication, Modbus, CAN, or MQTT.
- Runtime behavior, persistence, mutable operational state, or side effects.

## Architecture

EnergyAsset defines the shared identity and display name of a physical energy
component. BatteryAsset, PVAsset, and LoadAsset extend that immutable
definition only with explicit rated characteristics.

Assets contain no control methods, communication adapters, calculated state,
or runtime ownership. Future policies and controllers may consume these values
without changing their definitions.

## Acceptance Criteria

- Every asset is a frozen slotted dataclass.
- Asset identifiers and names are validated and immutable.
- Capacity and rated power constraints match the TASK-006 specification.
- Invalid types raise TypeError and invalid values raise ValueError.
- Error messages identify the invalid field.
- Public imports expose all four asset models.
- No operational or communication behavior is added.
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

Numeric inputs accept integers or floats, reject booleans, and are normalized
to floats. NaN fails the explicit positive or non-negative constraints.
Identifiers are supplied by callers and normalized through the existing
AssetId type. No asset value is generated implicitly.
