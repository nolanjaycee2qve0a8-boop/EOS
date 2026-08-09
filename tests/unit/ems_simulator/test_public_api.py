"""Tests for the EOS EMS Simulator application public API."""


def test_public_imports() -> None:
    from ems_simulator import (
        BatteryParameters,
        DailyEnergySummary,
        DailySimulationExport,
        DailySimulationResult,
        DailySimulationRunner,
        DailySimulationScenarioInput,
        GridEnergyBalanceSimulationModel,
        LoadProfileSimulationModel,
        PVProfileSimulationModel,
        SimpleBatteryPhysicsModel,
        SimulationExportPaths,
        SimulationResultExporter,
        SimulationVisualization,
    )

    assert BatteryParameters.__name__ == "BatteryParameters"
    assert DailyEnergySummary.__name__ == "DailyEnergySummary"
    assert DailySimulationExport.__name__ == "DailySimulationExport"
    assert DailySimulationResult.__name__ == "DailySimulationResult"
    assert DailySimulationRunner.__name__ == "DailySimulationRunner"
    assert DailySimulationScenarioInput.__name__ == "DailySimulationScenarioInput"
    assert (
        GridEnergyBalanceSimulationModel.__name__ == "GridEnergyBalanceSimulationModel"
    )
    assert LoadProfileSimulationModel.__name__ == "LoadProfileSimulationModel"
    assert PVProfileSimulationModel.__name__ == "PVProfileSimulationModel"
    assert SimpleBatteryPhysicsModel.__name__ == "SimpleBatteryPhysicsModel"
    assert SimulationExportPaths.__name__ == "SimulationExportPaths"
    assert SimulationResultExporter.__name__ == "SimulationResultExporter"
    assert SimulationVisualization.__name__ == "SimulationVisualization"
