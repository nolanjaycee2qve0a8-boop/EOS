"""Tests for the public EMS policy import boundary."""

from kernel.policy import EMSPolicy


def test_ems_policy_is_publicly_importable() -> None:
    assert EMSPolicy.__name__ == "EMSPolicy"
