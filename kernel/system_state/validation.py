"""Focused validation for immutable physical system state facts."""

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


def require_positive_number(value: object, field_name: str) -> float:
    """Require a finite number greater than zero."""
    normalized = require_number(value, field_name)
    if normalized <= 0:
        raise ValueError(f"{field_name} must be greater than 0")
    return normalized


def require_unit_interval(value: object, field_name: str) -> float:
    """Require a finite number in the inclusive interval from zero to one."""
    normalized = require_number(value, field_name)
    if not 0 <= normalized <= 1:
        raise ValueError(f"{field_name} must be between 0 and 1")
    return normalized


def require_non_empty_string(value: object, field_name: str) -> str:
    """Require a string containing non-whitespace text."""
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def require_instance[T](
    value: object,
    expected_type: type[T],
    field_name: str,
) -> T:
    """Require one exact runtime model type."""
    if not isinstance(value, expected_type):
        raise TypeError(f"{field_name} must be a {expected_type.__name__}")
    return value
