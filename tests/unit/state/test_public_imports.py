"""Tests for public energy state imports."""

from kernel.state import BatteryState, EnergySnapshot, LoadState, PVState


def test_state_models_are_publicly_importable() -> None:
    assert [
        model.__name__ for model in (BatteryState, PVState, LoadState, EnergySnapshot)
    ] == [
        "BatteryState",
        "PVState",
        "LoadState",
        "EnergySnapshot",
    ]
