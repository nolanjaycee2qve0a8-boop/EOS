"""Tests for the physical system state public API."""

import kernel.system_state as system_state
from kernel.system_state import (
    BatteryState,
    EnergySystemState,
    GridState,
    PCSState,
    PVState,
)


def test_system_state_models_are_publicly_importable() -> None:
    assert BatteryState.__name__ == "BatteryState"
    assert EnergySystemState.__name__ == "EnergySystemState"
    assert GridState.__name__ == "GridState"
    assert PCSState.__name__ == "PCSState"
    assert PVState.__name__ == "PVState"


def test_system_state_package_exports_only_task_027_models() -> None:
    assert system_state.__all__ == [
        "BatteryState",
        "EnergySystemState",
        "GridState",
        "PCSState",
        "PVState",
    ]
