"""Tests for the public energy-system context import boundary."""

from kernel.context import EnergySystemContext
from kernel.power import PowerFlow


def test_energy_system_context_is_publicly_importable() -> None:
    context = EnergySystemContext(
        assets=(),
        states=(),
        power_flow=PowerFlow(0.0, 0.0, 0.0, 0.0),
    )

    assert isinstance(context, EnergySystemContext)
