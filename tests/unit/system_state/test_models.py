"""Tests for immutable physical component state boundaries."""

from dataclasses import FrozenInstanceError, fields
from typing import Any, cast

import pytest

from kernel.system_state import BatteryState, GridState, PCSState, PVState

type ComponentState = BatteryState | PCSState | PVState | GridState


def make_battery_state(**overrides: object) -> BatteryState:
    values: dict[str, object] = {
        "soc": 0.5,
        "soh": 0.9,
        "voltage_v": 700.0,
        "current_a": -20.0,
        "temperature_c": 25.0,
        "available_charge_power_kw": 50.0,
        "available_discharge_power_kw": 60.0,
    }
    values.update(overrides)
    return BatteryState(**cast(Any, values))


def make_pcs_state(**overrides: object) -> PCSState:
    values: dict[str, object] = {
        "active_power_kw": 20.0,
        "reactive_power_kvar": -3.0,
        "operating_state": "running",
        "fault_state": "none",
    }
    values.update(overrides)
    return PCSState(**cast(Any, values))


def make_pv_state(**overrides: object) -> PVState:
    values: dict[str, object] = {
        "available_power_kw": 45.0,
        "actual_power_kw": 40.0,
    }
    values.update(overrides)
    return PVState(**cast(Any, values))


def make_grid_state(**overrides: object) -> GridState:
    values: dict[str, object] = {
        "grid_power_kw": 10.0,
        "voltage_v": 400.0,
        "frequency_hz": 50.0,
    }
    values.update(overrides)
    return GridState(**cast(Any, values))


@pytest.mark.parametrize(
    "state",
    [
        make_battery_state(),
        make_pcs_state(),
        make_pv_state(),
        make_grid_state(),
    ],
)
def test_component_states_are_frozen_and_slotted(state: ComponentState) -> None:
    assert not hasattr(state, "__dict__")
    assert tuple(field.name for field in fields(state)) == type(state).__slots__
    first_field = fields(state)[0].name
    with pytest.raises(FrozenInstanceError):
        setattr(cast(Any, state), first_field, getattr(state, first_field))


@pytest.mark.parametrize(
    "state",
    [
        make_battery_state(),
        make_pcs_state(),
        make_pv_state(),
        make_grid_state(),
    ],
)
def test_component_states_have_no_mutable_container_fields(
    state: ComponentState,
) -> None:
    assert not any(
        isinstance(getattr(state, field.name), list | dict | set)
        for field in fields(state)
    )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("soc", -0.1),
        ("soc", 1.1),
        ("soh", -0.1),
        ("soh", 1.1),
        ("voltage_v", -0.1),
        ("available_charge_power_kw", -0.1),
        ("available_discharge_power_kw", -0.1),
    ],
)
def test_battery_state_rejects_invalid_ranges(
    field_name: str,
    value: object,
) -> None:
    with pytest.raises(ValueError, match=field_name):
        make_battery_state(**{field_name: value})


@pytest.mark.parametrize("field_name", ["available_power_kw", "actual_power_kw"])
def test_pv_state_rejects_negative_power(field_name: str) -> None:
    with pytest.raises(ValueError, match=field_name):
        make_pv_state(**{field_name: -0.1})


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("voltage_v", -0.1),
        ("frequency_hz", 0.0),
    ],
)
def test_grid_state_rejects_invalid_ranges(
    field_name: str,
    value: object,
) -> None:
    with pytest.raises(ValueError, match=field_name):
        make_grid_state(**{field_name: value})


@pytest.mark.parametrize("field_name", ["operating_state", "fault_state"])
def test_pcs_state_rejects_empty_labels(field_name: str) -> None:
    with pytest.raises(ValueError, match=field_name):
        make_pcs_state(**{field_name: " "})


@pytest.mark.parametrize(
    ("factory", "field_name"),
    [
        (make_battery_state, "current_a"),
        (make_pcs_state, "active_power_kw"),
        (make_pcs_state, "reactive_power_kvar"),
        (make_grid_state, "grid_power_kw"),
    ],
)
def test_signed_observations_reject_non_finite_values(
    factory: Any,
    field_name: str,
) -> None:
    with pytest.raises(ValueError, match=field_name):
        factory(**{field_name: float("nan")})


def test_battery_unit_and_range_contract_is_documented() -> None:
    raw_documentation = BatteryState.__doc__

    assert raw_documentation is not None
    documentation = " ".join(raw_documentation.split())
    assert "unitless fractions in ``[0, 1]``" in documentation
    assert "Voltage is in V" in documentation
    assert "current is in A" in documentation
    assert "temperature is in degrees Celsius" in documentation
    assert "in kW" in documentation


def test_pcs_unit_and_sign_contract_is_documented() -> None:
    raw_documentation = PCSState.__doc__

    assert raw_documentation is not None
    documentation = " ".join(raw_documentation.split())
    assert "positive means AC output" in documentation
    assert "negative means AC absorption" in documentation
    assert "in kVAr" in documentation


def test_grid_unit_and_sign_contract_is_documented() -> None:
    raw_documentation = GridState.__doc__

    assert raw_documentation is not None
    documentation = " ".join(raw_documentation.split())
    assert "positive means importing from the grid" in documentation
    assert "negative means exporting to the grid" in documentation
    assert "zero means balanced exchange" in documentation
    assert "in V" in documentation
    assert "in Hz" in documentation


def test_pv_unit_contract_is_documented() -> None:
    raw_documentation = PVState.__doc__

    assert raw_documentation is not None
    documentation = " ".join(raw_documentation.split())
    assert "non-negative" in documentation
    assert "in kW" in documentation
