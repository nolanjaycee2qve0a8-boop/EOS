"""Validation for Phase 6 simulation identity and time contracts."""

from datetime import datetime
from math import isfinite


def require_sequence(value: object) -> int:
    """Require a non-boolean, non-negative integer sequence."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("sequence must be an int")
    if value < 0:
        raise ValueError("sequence must be greater than or equal to 0")
    return value


def require_positive_number(value: object, field_name: str) -> float:
    """Require a finite, non-boolean number greater than zero."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    if normalized <= 0:
        raise ValueError(f"{field_name} must be greater than 0")
    return normalized


def require_non_negative_number(value: object, field_name: str) -> float:
    """Require a finite, non-boolean number greater than or equal to zero."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    if normalized < 0:
        raise ValueError(f"{field_name} must be greater than or equal to 0")
    return normalized


def require_number(value: object, field_name: str) -> float:
    """Require a finite, non-boolean signed number."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    return normalized


def require_fraction(value: object, field_name: str) -> float:
    """Require a finite, non-boolean raw fraction in the closed range [0, 1]."""
    normalized = require_number(value, field_name)
    if not 0 <= normalized <= 1:
        raise ValueError(f"{field_name} must be between 0 and 1 inclusive")
    return normalized


def require_optional_timezone_aware_datetime(
    value: object,
    field_name: str,
) -> datetime | None:
    """Require explicit None or preserve an exact timezone-aware datetime."""
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime or None")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value
