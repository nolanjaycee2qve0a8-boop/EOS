"""Smoke tests for the initial package layout."""

import capability
import kernel
import optimization
import simulator


def test_top_level_packages_are_importable() -> None:
    """The configured top-level packages can be imported."""
    assert capability.__name__ == "capability"
    assert kernel.__name__ == "kernel"
    assert optimization.__name__ == "optimization"
    assert simulator.__name__ == "simulator"
