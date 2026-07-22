"""Focused runtime contract validation for the decision package."""

from collections.abc import Iterable, Mapping
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
