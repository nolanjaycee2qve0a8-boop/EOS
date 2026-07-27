"""Tests for public runtime kernel imports."""

from kernel.runtime import (
    DispatchedJournaledEMSTick,
    DispatchProgressionRuntime,
    ExecutionAudit,
    JournaledEMSRuntime,
    JournaledEMSTick,
    ReplayResult,
    RuntimeExecutionTrace,
    RuntimeKernel,
    RuntimeReplay,
    TickResult,
)


def test_runtime_interfaces_are_publicly_importable() -> None:
    assert DispatchProgressionRuntime.__name__ == "DispatchProgressionRuntime"
    assert DispatchedJournaledEMSTick.__name__ == "DispatchedJournaledEMSTick"
    assert ExecutionAudit.__name__ == "ExecutionAudit"
    assert JournaledEMSRuntime.__name__ == "JournaledEMSRuntime"
    assert JournaledEMSTick.__name__ == "JournaledEMSTick"
    assert ReplayResult.__name__ == "ReplayResult"
    assert RuntimeExecutionTrace.__name__ == "RuntimeExecutionTrace"
    assert RuntimeKernel.__name__ == "RuntimeKernel"
    assert RuntimeReplay.__name__ == "RuntimeReplay"
    assert TickResult.__name__ == "TickResult"
