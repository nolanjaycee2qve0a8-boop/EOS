"""Focused validation helpers for immutable energy state."""

from math import isfinite


def require_non_empty_string(value: object, field_name: str) -> str:
    """Require a string containing non-whitespace text."""
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def require_number(value: object, field_name: str) -> float:
    """Require a finite non-boolean numeric observation."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    return normalized


def require_unit_interval(value: object, field_name: str) -> float:
    """Require a finite number in the inclusive interval from zero to one."""
    normalized = require_number(value, field_name)
    if not 0 <= normalized <= 1:
        raise ValueError(f"{field_name} must be between 0 and 1")
    return normalized


def require_non_negative_number(value: object, field_name: str) -> float:
    """Require a finite number greater than or equal to zero."""
    normalized = require_number(value, field_name)
    if normalized < 0:
        raise ValueError(f"{field_name} must be greater than or equal to 0")
    return normalized


def require_tuple_of[T](
    value: object,
    expected_type: type[T],
    field_name: str,
) -> tuple[T, ...]:
    """Require a tuple containing only values of one runtime type."""
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    for item in value:
        if not isinstance(item, expected_type):
            raise TypeError(
                f"{field_name} must contain only {expected_type.__name__} instances"
            )
    return value
