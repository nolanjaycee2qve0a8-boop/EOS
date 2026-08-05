"""Tests for the Phase 6 simulation public API."""

from simulator import (
    PVSimulationInput,
    PVSimulationModelBoundary,
    PVSimulationResult,
    SimulationStepIdentity,
)
from simulator import __all__ as public_names


def test_simulation_step_identity_public_import() -> None:
    step = SimulationStepIdentity(sequence=0, duration_seconds=1.0, timestamp=None)

    assert step.sequence == 0
    assert public_names == [
        "PVSimulationInput",
        "PVSimulationModelBoundary",
        "PVSimulationResult",
        "SimulationStepIdentity",
    ]


def test_pv_contract_public_imports() -> None:
    simulation_input = PVSimulationInput(
        SimulationStepIdentity(0, 1.0, None),
        2.0,
    )

    result = PVSimulationResult(simulation_input, 1.0)

    assert result.simulation_input is simulation_input
    assert PVSimulationModelBoundary.__name__ == "PVSimulationModelBoundary"
