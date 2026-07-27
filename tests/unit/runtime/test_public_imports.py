"""Tests for public runtime kernel imports."""

from kernel.runtime import (
    DispatchedJournaledEMSTick,
    DispatchProgressionRuntime,
    JournaledEMSRuntime,
    JournaledEMSTick,
    RuntimeExecutionTrace,
    RuntimeKernel,
    TickResult,
)


def test_runtime_interfaces_are_publicly_importable() -> None:
    assert DispatchProgressionRuntime.__name__ == "DispatchProgressionRuntime"
    assert DispatchedJournaledEMSTick.__name__ == "DispatchedJournaledEMSTick"
    assert JournaledEMSRuntime.__name__ == "JournaledEMSRuntime"
    assert JournaledEMSTick.__name__ == "JournaledEMSTick"
    assert RuntimeExecutionTrace.__name__ == "RuntimeExecutionTrace"
    assert RuntimeKernel.__name__ == "RuntimeKernel"
    assert TickResult.__name__ == "TickResult"
