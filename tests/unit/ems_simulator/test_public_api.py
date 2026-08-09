"""Tests for the EOS EMS Simulator application public API."""


def test_public_imports() -> None:
    from ems_simulator import (
        BatteryParameters,
        DailySimulationScenarioInput,
        LoadProfileSimulationModel,
        PVProfileSimulationModel,
        SimpleBatteryPhysicsModel,
    )

    assert BatteryParameters.__name__ == "BatteryParameters"
    assert DailySimulationScenarioInput.__name__ == "DailySimulationScenarioInput"
    assert LoadProfileSimulationModel.__name__ == "LoadProfileSimulationModel"
    assert PVProfileSimulationModel.__name__ == "PVProfileSimulationModel"
    assert SimpleBatteryPhysicsModel.__name__ == "SimpleBatteryPhysicsModel"
