"""Tests for the EOS EMS Simulator application public API."""


def test_public_imports() -> None:
    from ems_simulator import (
        BatteryParameters,
        DailyEnergySummary,
        DailySimulationExport,
        DailySimulationResult,
        DailySimulationRunner,
        DailySimulationScenarioInput,
        EMSIntegrationResult,
        EMSIntegrationRunner,
        EMSIntegrationScenarioInput,
        EMSIntegrationStepTrace,
        ExplainableMPCDailySimulationBoundary,
        ExplainableMPCDailySimulationInput,
        ExplainableMPCDailySimulationResult,
        ExplainableMPCDailySimulationRunner,
        ExplainableMPCDailySimulationStepTrace,
        GridEnergyBalanceSimulationModel,
        HeadroomAwareExplainableMPCDailySimulationBoundary,
        HeadroomAwareExplainableMPCDailySimulationResult,
        HeadroomAwareExplainableMPCDailySimulationRunner,
        HeadroomAwareExplainableMPCDailySimulationStepTrace,
        LoadProfileSimulationModel,
        PVProfileSimulationModel,
        RollingHeadroomAwareExplainableMPCDailySimulationBoundary,
        RollingHeadroomAwareExplainableMPCDailySimulationResult,
        RollingHeadroomAwareExplainableMPCDailySimulationRunner,
        RollingHeadroomAwareExplainableMPCDailySimulationStepTrace,
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
    assert EMSIntegrationResult.__name__ == "EMSIntegrationResult"
    assert EMSIntegrationRunner.__name__ == "EMSIntegrationRunner"
    assert EMSIntegrationScenarioInput.__name__ == "EMSIntegrationScenarioInput"
    assert EMSIntegrationStepTrace.__name__ == "EMSIntegrationStepTrace"
    assert (
        ExplainableMPCDailySimulationBoundary.__name__
        == "ExplainableMPCDailySimulationBoundary"
    )
    assert (
        ExplainableMPCDailySimulationInput.__name__
        == "ExplainableMPCDailySimulationInput"
    )
    assert (
        ExplainableMPCDailySimulationResult.__name__
        == "ExplainableMPCDailySimulationResult"
    )
    assert (
        ExplainableMPCDailySimulationRunner.__name__
        == "ExplainableMPCDailySimulationRunner"
    )
    assert (
        ExplainableMPCDailySimulationStepTrace.__name__
        == "ExplainableMPCDailySimulationStepTrace"
    )
    assert (
        GridEnergyBalanceSimulationModel.__name__ == "GridEnergyBalanceSimulationModel"
    )
    assert (
        HeadroomAwareExplainableMPCDailySimulationBoundary.__name__
        == "HeadroomAwareExplainableMPCDailySimulationBoundary"
    )
    assert (
        HeadroomAwareExplainableMPCDailySimulationResult.__name__
        == "HeadroomAwareExplainableMPCDailySimulationResult"
    )
    assert (
        HeadroomAwareExplainableMPCDailySimulationRunner.__name__
        == "HeadroomAwareExplainableMPCDailySimulationRunner"
    )
    assert (
        HeadroomAwareExplainableMPCDailySimulationStepTrace.__name__
        == "HeadroomAwareExplainableMPCDailySimulationStepTrace"
    )
    assert (
        RollingHeadroomAwareExplainableMPCDailySimulationBoundary.__name__
        == "RollingHeadroomAwareExplainableMPCDailySimulationBoundary"
    )
    assert (
        RollingHeadroomAwareExplainableMPCDailySimulationResult.__name__
        == "RollingHeadroomAwareExplainableMPCDailySimulationResult"
    )
    assert (
        RollingHeadroomAwareExplainableMPCDailySimulationRunner.__name__
        == "RollingHeadroomAwareExplainableMPCDailySimulationRunner"
    )
    assert (
        RollingHeadroomAwareExplainableMPCDailySimulationStepTrace.__name__
        == "RollingHeadroomAwareExplainableMPCDailySimulationStepTrace"
    )
    assert LoadProfileSimulationModel.__name__ == "LoadProfileSimulationModel"
    assert PVProfileSimulationModel.__name__ == "PVProfileSimulationModel"
    assert SimpleBatteryPhysicsModel.__name__ == "SimpleBatteryPhysicsModel"
    assert SimulationExportPaths.__name__ == "SimulationExportPaths"
    assert SimulationResultExporter.__name__ == "SimulationResultExporter"
    assert SimulationVisualization.__name__ == "SimulationVisualization"
