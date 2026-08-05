"""Tests for the Phase 6 simulation public API."""

from datetime import UTC, datetime

from simulator import (
    LoadSimulationInput,
    LoadSimulationModelBoundary,
    LoadSimulationResult,
    PVSimulationInput,
    PVSimulationModelBoundary,
    PVSimulationResult,
    SimulationStepIdentity,
    TariffSimulationInput,
    TariffSimulationModelBoundary,
    TariffSimulationResult,
)
from simulator import __all__ as public_names


def test_simulation_step_identity_public_import() -> None:
    step = SimulationStepIdentity(sequence=0, duration_seconds=1.0, timestamp=None)

    assert step.sequence == 0
    assert public_names == [
        "LoadSimulationInput",
        "LoadSimulationModelBoundary",
        "LoadSimulationResult",
        "PVSimulationInput",
        "PVSimulationModelBoundary",
        "PVSimulationResult",
        "SimulationStepIdentity",
        "TariffSimulationInput",
        "TariffSimulationModelBoundary",
        "TariffSimulationResult",
    ]


def test_pv_contract_public_imports() -> None:
    simulation_input = PVSimulationInput(
        SimulationStepIdentity(0, 1.0, None),
        2.0,
    )

    result = PVSimulationResult(simulation_input, 1.0)

    assert result.simulation_input is simulation_input
    assert PVSimulationModelBoundary.__name__ == "PVSimulationModelBoundary"


def test_load_contract_public_imports() -> None:
    simulation_input = LoadSimulationInput(
        SimulationStepIdentity(0, 1.0, None),
        2.0,
    )
    result = LoadSimulationResult(simulation_input, 1.0)

    assert result.simulation_input is simulation_input
    assert LoadSimulationModelBoundary.__name__ == "LoadSimulationModelBoundary"


def test_tariff_contract_public_imports() -> None:
    simulation_input = TariffSimulationInput(
        SimulationStepIdentity(0, 1.0, datetime(2026, 8, 5, tzinfo=UTC)),
        0.8,
        0.3,
    )
    result = TariffSimulationResult(simulation_input, 0.8, 0.3)

    assert result.simulation_input is simulation_input
    assert TariffSimulationModelBoundary.__name__ == "TariffSimulationModelBoundary"
