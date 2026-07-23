# TASK-008 — Immutable Power Flow Model

## Status

IN REVIEW

## Objective

Introduce an immutable, deterministic observation of the power exchanged by
PV generation, load consumption, a battery, and the grid.

## Scope

- PowerFlow with explicit PV, load, battery, and grid power values.
- A documented sign convention and enforced power-balance invariant.
- Focused finite-number validation and a stable public import.
- Unit tests covering valid flows, invalid observations, and immutability.

## Non-goals

- EMS policy, optimization, scheduling, or forecasting.
- SOC calculation, battery modeling, or PCS control.
- Zero-export control, pricing, or runtime behavior.
- Telemetry, persistence, or device communication.

## Sign Convention

- PV power is non-negative generation.
- Load power is non-negative consumption.
- Negative battery power means charging.
- Positive battery power means discharging.
- Positive grid power means import.
- Negative grid power means export.

PowerFlow enforces:

`pv_power_kw + grid_power_kw + battery_power_kw = load_power_kw`

The equality check uses a fixed absolute tolerance of `1e-9 kW` and no relative
tolerance. It accepts ordinary binary floating-point rounding while keeping
validation independent of system size. PowerFlow never adjusts caller values
to create a balance.

## Acceptance Criteria

- PowerFlow is a frozen slotted dataclass with only the specified fields.
- Numeric inputs accept non-boolean integers or floats and normalize to floats.
- Every power value is finite.
- PV and load power are non-negative.
- Battery and grid power preserve signed values.
- Invalid types raise TypeError; invalid values and imbalance raise ValueError.
- Public imports support `from kernel.power import PowerFlow`.
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

PowerFlow is an observation only. It performs explicit validation but contains
no policy, controller, hidden calculation, or automatic correction.
