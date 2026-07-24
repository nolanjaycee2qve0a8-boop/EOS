"""Tests for public runtime kernel imports."""

from kernel.runtime import (
    JournaledEMSRuntime,
    JournaledEMSTick,
    RuntimeKernel,
    TickResult,
)


def test_runtime_interfaces_are_publicly_importable() -> None:
    assert JournaledEMSRuntime.__name__ == "JournaledEMSRuntime"
    assert JournaledEMSTick.__name__ == "JournaledEMSTick"
    assert RuntimeKernel.__name__ == "RuntimeKernel"
    assert TickResult.__name__ == "TickResult"
