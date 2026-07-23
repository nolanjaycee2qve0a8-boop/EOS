"""Tests for immutable BatteryAsset definitions."""

from dataclasses import FrozenInstanceError, fields
from typing import Any, cast

import pytest

from kernel.asset import BatteryAsset, EnergyAsset
from kernel.ids import AssetId


def make_battery() -> BatteryAsset:
    return BatteryAsset(
        asset_id=AssetId("battery-1"),
        name="Main battery",
        capacity_kwh=100,
        max_charge_kw=40,
        max_discharge_kw=50,
    )


def test_battery_asset_creation() -> None:
    asset = make_battery()
    assert isinstance(asset, EnergyAsset)
    assert asset.capacity_kwh == 100.0
    assert asset.max_charge_kw == 40.0
    assert asset.max_discharge_kw == 50.0


def test_battery_asset_allows_zero_power_limits() -> None:
    asset = BatteryAsset(AssetId("battery-1"), "Battery", 100, 0, 0)
    assert asset.max_charge_kw == 0.0
    assert asset.max_discharge_kw == 0.0


@pytest.mark.parametrize("capacity_kwh", [0, -1, float("nan")])
def test_battery_asset_rejects_invalid_capacity(capacity_kwh: float) -> None:
    with pytest.raises(ValueError, match="capacity_kwh"):
        BatteryAsset(AssetId("battery-1"), "Battery", capacity_kwh, 10, 10)


def test_battery_asset_rejects_invalid_capacity_type() -> None:
    with pytest.raises(TypeError, match="capacity_kwh"):
        BatteryAsset(
            AssetId("battery-1"),
            "Battery",
            cast(float, "100"),
            10,
            10,
        )


@pytest.mark.parametrize("max_charge_kw", [-1, float("nan")])
def test_battery_asset_rejects_invalid_charge_power(max_charge_kw: float) -> None:
    with pytest.raises(ValueError, match="max_charge_kw"):
        BatteryAsset(AssetId("battery-1"), "Battery", 100, max_charge_kw, 10)


def test_battery_asset_rejects_invalid_charge_power_type() -> None:
    with pytest.raises(TypeError, match="max_charge_kw"):
        BatteryAsset(
            AssetId("battery-1"),
            "Battery",
            100,
            cast(float, True),
            10,
        )


@pytest.mark.parametrize("max_discharge_kw", [-1, float("nan")])
def test_battery_asset_rejects_invalid_discharge_power(
    max_discharge_kw: float,
) -> None:
    with pytest.raises(ValueError, match="max_discharge_kw"):
        BatteryAsset(AssetId("battery-1"), "Battery", 100, 10, max_discharge_kw)


def test_battery_asset_rejects_invalid_discharge_power_type() -> None:
    with pytest.raises(TypeError, match="max_discharge_kw"):
        BatteryAsset(
            AssetId("battery-1"),
            "Battery",
            100,
            10,
            cast(float, object()),
        )


def test_battery_asset_is_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        cast(Any, make_battery()).capacity_kwh = 200


def test_battery_asset_uses_slots() -> None:
    assert not hasattr(make_battery(), "__dict__")


def test_battery_asset_excludes_operational_state() -> None:
    assert [field.name for field in fields(BatteryAsset)] == [
        "asset_id",
        "name",
        "capacity_kwh",
        "max_charge_kw",
        "max_discharge_kw",
    ]
