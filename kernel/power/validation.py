"""Focused validation helpers for immutable power observations."""

from math import isfinite


def require_number(value: object, field_name: str) -> float:
    """Require a finite non-boolean integer or float."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    return normalized


def require_non_negative_number(value: object, field_name: str) -> float:
    """Require a finite number greater than or equal to zero."""
    normalized = require_number(value, field_name)
    if normalized < 0:
        raise ValueError(f"{field_name} must be greater than or equal to 0")
    return normalized
