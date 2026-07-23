"""Tests for the public execution adapter import boundary."""

from kernel.execution import PolicyExecutor


def test_policy_executor_is_publicly_importable() -> None:
    assert PolicyExecutor.__name__ == "PolicyExecutor"
