"""Tests for public runtime kernel imports."""

from kernel.runtime import RuntimeKernel, TickResult


def test_runtime_interfaces_are_publicly_importable() -> None:
    assert RuntimeKernel.__name__ == "RuntimeKernel"
    assert TickResult.__name__ == "TickResult"
