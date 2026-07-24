"""Tests for the public EMS cycle import boundary."""

from kernel.cycle import EMSCycle, JournaledEMSCycle


def test_ems_cycle_is_publicly_importable() -> None:
    assert EMSCycle.__name__ == "EMSCycle"


def test_journaled_ems_cycle_is_publicly_importable() -> None:
    assert JournaledEMSCycle.__name__ == "JournaledEMSCycle"
