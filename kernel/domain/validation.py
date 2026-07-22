"""Shared validation primitives for immutable EOS domain objects."""

from collections.abc import Mapping
from datetime import datetime
from types import MappingProxyType


def require_non_empty_string(value: str, field_name: str) -> str:
    """Return a string after ensuring that it contains non-whitespace text."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def require_timezone_aware(value: datetime, field_name: str) -> datetime:
    """Return a datetime after ensuring that its UTC offset is defined."""
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    if value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    return value


def require_non_negative_integer(value: int, field_name: str) -> int:
    """Return an integer after ensuring that it is non-negative and not bool."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def freeze_mapping(
    value: Mapping[str, object], field_name: str
) -> Mapping[str, object]:
    """Return a read-only, shallow defensive copy of a string-keyed mapping."""
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")

    copied: dict[str, object] = {}
    for key, item in value.items():
        require_non_empty_string(key, f"{field_name} key")
        copied[key] = item
    return MappingProxyType(copied)
