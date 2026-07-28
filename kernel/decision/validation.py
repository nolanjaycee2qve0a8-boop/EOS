"""Focused runtime contract validation for the decision package."""

from collections.abc import Iterable, Mapping
from datetime import datetime
from math import isfinite
from typing import cast


def require_typed_iterable[T](
    value: object,
    expected_type: type[T],
    field_name: str,
) -> tuple[T, ...]:
    """Validate and defensively normalize an iterable to a typed tuple."""
    if isinstance(value, str | bytes | bytearray | Mapping) or not isinstance(
        value, Iterable
    ):
        raise TypeError(f"{field_name} must be an iterable of {expected_type.__name__}")

    normalized = tuple(value)
    for item in normalized:
        if not isinstance(item, expected_type):
            raise TypeError(
                f"{field_name} must contain only {expected_type.__name__} instances"
            )
    return cast(tuple[T, ...], normalized)


def require_timezone_aware_datetime(
    value: object,
    field_name: str,
) -> datetime:
    """Require a datetime whose UTC offset is defined."""
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


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
