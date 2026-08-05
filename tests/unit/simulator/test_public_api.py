"""Tests for the Phase 6 simulation public API."""

from simulator import SimulationStepIdentity
from simulator import __all__ as public_names


def test_simulation_step_identity_public_import() -> None:
    step = SimulationStepIdentity(sequence=0, duration_seconds=1.0, timestamp=None)

    assert step.sequence == 0
    assert public_names == ["SimulationStepIdentity"]
