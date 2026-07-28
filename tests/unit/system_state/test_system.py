"""Tests for the immutable EnergySystemState aggregate."""

from dataclasses import FrozenInstanceError, fields
from typing import Any, cast

import pytest

from kernel.system_state import (
    BatteryState,
    EnergySystemState,
    GridState,
    PCSState,
    PVState,
)


def make_components() -> tuple[BatteryState, PCSState, PVState, GridState]:
    return (
        BatteryState(0.5, 0.9, 700.0, -20.0, 25.0, 50.0, 60.0),
        PCSState(20.0, -3.0, "running", "none"),
        PVState(45.0, 40.0),
        GridState(10.0, 400.0, 50.0),
    )


def test_system_state_preserves_exact_component_identities() -> None:
    battery, pcs, pv, grid = make_components()

    state = EnergySystemState(battery, pcs, pv, grid)

    assert state.battery_state is battery
    assert state.pcs_state is pcs
    assert state.pv_state is pv
    assert state.grid_state is grid


def test_system_state_is_frozen_slotted_and_has_exact_fields() -> None:
    state = EnergySystemState(*make_components())

    assert tuple(field.name for field in fields(EnergySystemState)) == (
        "battery_state",
        "pcs_state",
        "pv_state",
        "grid_state",
    )
    assert EnergySystemState.__slots__ == (
        "battery_state",
        "pcs_state",
        "pv_state",
        "grid_state",
    )
    assert not hasattr(state, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, state).battery_state = state.battery_state


def test_system_state_has_no_mutable_container_fields() -> None:
    state = EnergySystemState(*make_components())

    assert not any(
        isinstance(getattr(state, field.name), list | dict | set)
        for field in fields(EnergySystemState)
    )


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("battery_state", object()),
        ("pcs_state", object()),
        ("pv_state", object()),
        ("grid_state", object()),
    ],
)
def test_system_state_rejects_invalid_component_types(
    field_name: str,
    invalid_value: object,
) -> None:
    components = dict(
        zip(
            ("battery_state", "pcs_state", "pv_state", "grid_state"),
            make_components(),
            strict=True,
        )
    )
    components[field_name] = invalid_value

    with pytest.raises(TypeError, match=field_name):
        EnergySystemState(**cast(Any, components))


def test_system_state_does_not_define_execution_behavior() -> None:
    forbidden_methods = (
        "optimize",
        "forecast",
        "dispatch",
        "execute",
        "control",
    )

    assert not any(hasattr(EnergySystemState, name) for name in forbidden_methods)
