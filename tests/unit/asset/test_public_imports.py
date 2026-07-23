"""Tests for public energy asset imports."""

from kernel.asset import BatteryAsset, EnergyAsset, LoadAsset, PVAsset


def test_asset_models_are_publicly_importable() -> None:
    assert [
        model.__name__ for model in (EnergyAsset, BatteryAsset, PVAsset, LoadAsset)
    ] == [
        "EnergyAsset",
        "BatteryAsset",
        "PVAsset",
        "LoadAsset",
    ]
