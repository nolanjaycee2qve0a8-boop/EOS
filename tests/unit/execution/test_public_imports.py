"""Tests for the public execution adapter import boundary."""

from kernel.execution import JournaledEMSExecutionService, PolicyExecutor


def test_policy_executor_is_publicly_importable() -> None:
    assert PolicyExecutor.__name__ == "PolicyExecutor"


def test_journaled_execution_service_is_publicly_importable() -> None:
    assert JournaledEMSExecutionService.__name__ == "JournaledEMSExecutionService"
