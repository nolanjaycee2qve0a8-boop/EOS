"""Tests for immutable BatteryState observations."""

from dataclasses import FrozenInstanceError, fields
from typing import Any, cast

import pytest

from kernel.ids import AssetId
from kernel.state import BatteryState


def test_battery_state_creation() -> None:
    state = BatteryState(AssetId("battery-1"), 0.5, -20)
    assert state.asset_id == AssetId("battery-1")
    assert state.soc == 0.5
    assert state.power_kw == -20.0


@pytest.mark.parametrize("soc", [0, 1])
def test_battery_state_accepts_soc_boundaries(soc: float) -> None:
    assert BatteryState(AssetId("battery-1"), soc, 0).soc == float(soc)


@pytest.mark.parametrize(
    "soc",
    [-0.01, 1.01, float("nan"), float("inf"), float("-inf")],
)
def test_battery_state_rejects_invalid_soc(soc: float) -> None:
    with pytest.raises(ValueError, match="soc"):
        BatteryState(AssetId("battery-1"), soc, 0)


@pytest.mark.parametrize("soc", [True, "0.5", None])
def test_battery_state_rejects_invalid_soc_type(soc: object) -> None:
    with pytest.raises(TypeError, match="soc"):
        BatteryState(AssetId("battery-1"), cast(float, soc), 0)


@pytest.mark.parametrize("power_kw", [-20, 0, 20])
def test_battery_state_accepts_signed_power(power_kw: float) -> None:
    assert BatteryState(AssetId("battery-1"), 0.5, power_kw).power_kw == float(power_kw)


@pytest.mark.parametrize("power_kw", [float("nan"), float("inf")])
def test_battery_state_rejects_non_finite_power(power_kw: float) -> None:
    with pytest.raises(ValueError, match="power_kw"):
        BatteryState(AssetId("battery-1"), 0.5, power_kw)


def test_battery_state_rejects_invalid_power_type() -> None:
    with pytest.raises(TypeError, match="power_kw"):
        BatteryState(AssetId("battery-1"), 0.5, cast(float, True))


def test_battery_state_rejects_empty_asset_id() -> None:
    with pytest.raises(ValueError, match="asset_id"):
        BatteryState(AssetId(""), 0.5, 0)


def test_battery_state_is_frozen_and_slotted() -> None:
    state = BatteryState(AssetId("battery-1"), 0.5, 0)
    assert not hasattr(state, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, state).soc = 0.6


def test_battery_state_has_only_observation_fields() -> None:
    assert [field.name for field in fields(BatteryState)] == [
        "asset_id",
        "soc",
        "power_kw",
    ]
