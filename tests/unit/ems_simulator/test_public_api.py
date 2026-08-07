"""Tests for the EOS EMS Simulator application public API."""


def test_public_imports() -> None:
    from ems_simulator import BatteryParameters, DailySimulationScenarioInput

    assert BatteryParameters.__name__ == "BatteryParameters"
    assert DailySimulationScenarioInput.__name__ == "DailySimulationScenarioInput"
