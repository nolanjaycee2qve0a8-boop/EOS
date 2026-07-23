"""Tests for immutable balanced power observations."""

from dataclasses import FrozenInstanceError, fields
from math import inf, nan
from typing import Any

import pytest

from kernel.power import PowerFlow


def test_creates_valid_power_flow() -> None:
    flow = PowerFlow(
        pv_power_kw=8,
        load_power_kw=10,
        battery_power_kw=1,
        grid_power_kw=1,
    )

    assert flow.pv_power_kw == 8.0
    assert flow.load_power_kw == 10.0
    assert flow.battery_power_kw == 1.0
    assert flow.grid_power_kw == 1.0


@pytest.mark.parametrize(
    ("pv_power_kw", "load_power_kw", "battery_power_kw", "grid_power_kw"),
    [
        (10.0, 10.0, 0.0, 0.0),
        (0.0, 5.0, 5.0, 0.0),
        (10.0, 7.0, -3.0, 0.0),
        (0.0, 8.0, 0.0, 8.0),
        (10.0, 7.0, 0.0, -3.0),
    ],
    ids=[
        "pv-supplies-load",
        "battery-discharge-supplies-load",
        "battery-charges-from-pv",
        "grid-import-supplies-load",
        "pv-exports-to-grid",
    ],
)
def test_accepts_balanced_sign_conventions(
    pv_power_kw: float,
    load_power_kw: float,
    battery_power_kw: float,
    grid_power_kw: float,
) -> None:
    flow = PowerFlow(
        pv_power_kw=pv_power_kw,
        load_power_kw=load_power_kw,
        battery_power_kw=battery_power_kw,
        grid_power_kw=grid_power_kw,
    )

    assert (
        flow.pv_power_kw + flow.grid_power_kw + flow.battery_power_kw
        == pytest.approx(flow.load_power_kw)
    )


def test_accepts_floating_point_rounding_within_fixed_tolerance() -> None:
    flow = PowerFlow(
        pv_power_kw=0.1,
        load_power_kw=0.3,
        battery_power_kw=0.0,
        grid_power_kw=0.2,
    )

    assert flow.load_power_kw == 0.3


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("pv_power_kw", -0.1),
        ("load_power_kw", -0.1),
    ],
)
def test_rejects_negative_unsigned_power(field_name: str, value: float) -> None:
    values: dict[str, Any] = {
        "pv_power_kw": 1.0,
        "load_power_kw": 1.0,
        "battery_power_kw": 0.0,
        "grid_power_kw": 0.0,
    }
    values[field_name] = value

    with pytest.raises(ValueError, match=field_name):
        PowerFlow(**values)


@pytest.mark.parametrize(
    "field_name",
    ["pv_power_kw", "load_power_kw", "battery_power_kw", "grid_power_kw"],
)
@pytest.mark.parametrize("value", [True, False])
def test_rejects_bool(field_name: str, value: bool) -> None:
    values: dict[str, Any] = {
        "pv_power_kw": 1.0,
        "load_power_kw": 1.0,
        "battery_power_kw": 0.0,
        "grid_power_kw": 0.0,
    }
    values[field_name] = value

    with pytest.raises(TypeError, match=field_name):
        PowerFlow(**values)


@pytest.mark.parametrize(
    "field_name",
    ["pv_power_kw", "load_power_kw", "battery_power_kw", "grid_power_kw"],
)
def test_rejects_non_numeric_values(field_name: str) -> None:
    values: dict[str, Any] = {
        "pv_power_kw": 1.0,
        "load_power_kw": 1.0,
        "battery_power_kw": 0.0,
        "grid_power_kw": 0.0,
    }
    values[field_name] = "1.0"

    with pytest.raises(TypeError, match=field_name):
        PowerFlow(**values)


@pytest.mark.parametrize(
    "field_name",
    ["pv_power_kw", "load_power_kw", "battery_power_kw", "grid_power_kw"],
)
@pytest.mark.parametrize("value", [nan, inf, -inf])
def test_rejects_non_finite_values(field_name: str, value: float) -> None:
    values: dict[str, Any] = {
        "pv_power_kw": 1.0,
        "load_power_kw": 1.0,
        "battery_power_kw": 0.0,
        "grid_power_kw": 0.0,
    }
    values[field_name] = value

    with pytest.raises(ValueError, match=field_name):
        PowerFlow(**values)


def test_rejects_power_imbalance_beyond_fixed_tolerance() -> None:
    with pytest.raises(ValueError, match="power balance"):
        PowerFlow(
            pv_power_kw=1.0,
            load_power_kw=1.0 + 1.1e-9,
            battery_power_kw=0.0,
            grid_power_kw=0.0,
        )


def test_is_frozen() -> None:
    flow = PowerFlow(1.0, 1.0, 0.0, 0.0)

    with pytest.raises(FrozenInstanceError):
        flow.load_power_kw = 2.0  # type: ignore[misc]


def test_uses_slots_without_instance_dictionary() -> None:
    flow = PowerFlow(1.0, 1.0, 0.0, 0.0)

    assert not hasattr(flow, "__dict__")


def test_has_only_specified_fields() -> None:
    assert [field.name for field in fields(PowerFlow)] == [
        "pv_power_kw",
        "load_power_kw",
        "battery_power_kw",
        "grid_power_kw",
    ]
