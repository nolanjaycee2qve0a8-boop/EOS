"""Small, transport-neutral validation primitives for Edge contracts."""

from collections.abc import Iterable
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from math import isfinite
from types import UnionType
from typing import Any, ClassVar, Union, get_args, get_origin, get_type_hints


def require_non_empty_string(value: object, field_name: str) -> str:
    """Require non-blank text without normalizing caller-owned values."""
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
    return value


def require_non_negative_int(value: object, field_name: str) -> int:
    """Require a non-boolean non-negative sequence-like integer."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an int")
    if value < 0:
        raise ValueError(f"{field_name} must be greater than or equal to 0")
    return value


def require_number(value: object, field_name: str) -> float:
    """Require a finite non-boolean signed numeric value."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    return normalized


def require_non_negative_number(value: object, field_name: str) -> float:
    """Require a finite non-negative numeric value."""
    normalized = require_number(value, field_name)
    if normalized < 0:
        raise ValueError(f"{field_name} must be greater than or equal to 0")
    return normalized


def require_fraction(value: object, field_name: str) -> float:
    """Require a finite fraction in the closed range [0, 1]."""
    normalized = require_number(value, field_name)
    if not 0 <= normalized <= 1:
        raise ValueError(f"{field_name} must be between 0 and 1 inclusive")
    return normalized


def require_aware_datetime(value: object, field_name: str) -> datetime:
    """Require a timezone-aware datetime and preserve the exact object."""
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def require_optional_aware_datetime(value: object, field_name: str) -> datetime | None:
    """Require explicit unknown (None) or a timezone-aware datetime."""
    if value is None:
        return None
    return require_aware_datetime(value, field_name)


def require_positive_timedelta(value: object, field_name: str) -> timedelta:
    """Require a positive duration without accepting bool-like alternatives."""
    if not isinstance(value, timedelta):
        raise TypeError(f"{field_name} must be a timedelta")
    if value <= timedelta(0):
        raise ValueError(f"{field_name} must be greater than zero")
    return value


def utc_isoformat(value: datetime) -> str:
    """Serialize one aware timestamp in canonical UTC ISO-8601 form."""
    return require_aware_datetime(value, "timestamp").astimezone(UTC).isoformat()


def parse_utc_datetime(value: object, field_name: str) -> datetime:
    """Parse a serialized datetime and require an explicit timezone offset."""
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be an ISO-8601 string")
    parsed = datetime.fromisoformat(value)
    return require_aware_datetime(parsed, field_name)


def require_exact_fields(
    value: object,
    field_name: str,
    expected_fields: Iterable[str],
) -> dict[str, object]:
    """Require an object with exactly the documented serialized fields."""
    if not isinstance(value, dict):
        raise TypeError(f"{field_name} must be a dict")
    expected = frozenset(expected_fields)
    actual = frozenset(value)
    missing = expected - actual
    unexpected = actual - expected
    if missing:
        raise ValueError(f"{field_name} missing fields: {sorted(missing)}")
    if unexpected:
        raise ValueError(f"{field_name} has unknown fields: {sorted(unexpected)}")
    return value


def timedelta_seconds(value: timedelta) -> float:
    """Serialize a positive caller-supplied duration in explicit seconds."""
    return require_positive_timedelta(value, "duration").total_seconds()


def parse_positive_timedelta(value: object, field_name: str) -> timedelta:
    """Parse one finite positive duration expressed in seconds."""
    seconds = require_number(value, field_name)
    return (
        timedelta(seconds=seconds)
        if seconds > 0
        else _raise_non_positive_duration(field_name)
    )


def _raise_non_positive_duration(field_name: str) -> timedelta:
    raise ValueError(f"{field_name} must be greater than zero")


class SerializableContract:
    """Strict, deterministic primitive serialization for immutable data facts.

    Services deliberately do not inherit this mixin.  Nested immutable facts use
    their own schemas, so audit snapshots cannot depend on Python repr values,
    object identities or local paths.
    """

    SCHEMA_VERSION: ClassVar[str]

    def to_dict(self) -> dict[str, object]:
        if not is_dataclass(self):
            raise TypeError("SerializableContract must be a dataclass")
        return {
            "schema_version": self.SCHEMA_VERSION,
            **{
                field.name: _serialize_primitive(getattr(self, field.name))
                for field in fields(self)
            },
        }

    @classmethod
    def from_dict(cls, value: object) -> Any:
        if not is_dataclass(cls):
            raise TypeError("SerializableContract must be a dataclass type")
        payload = require_exact_fields(
            value,
            cls.__name__,
            ("schema_version", *(field.name for field in fields(cls))),
        )
        if payload["schema_version"] != cls.SCHEMA_VERSION:
            raise ValueError(f"unsupported {cls.__name__} schema_version")
        hints = get_type_hints(cls)
        return cls(
            **{
                field.name: _deserialize_primitive(
                    payload[field.name], hints[field.name], field.name
                )
                for field in fields(cls)
            }
        )


def _serialize_primitive(value: object) -> object:
    if isinstance(value, datetime):
        return utc_isoformat(value)
    if isinstance(value, timedelta):
        return {"seconds": timedelta_seconds(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, SerializableContract) or hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, tuple):
        return [_serialize_primitive(item) for item in value]
    if value is None or isinstance(value, str | bool | int | float):
        return value
    raise TypeError(f"unsupported serialized value {type(value).__name__}")


def _deserialize_primitive(
    value: object, annotation: object, field_name: str
) -> object:
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        options = get_args(annotation)
        if value is None and type(None) in options:
            return None
        non_none = tuple(item for item in options if item is not type(None))
        if len(non_none) != 1:
            raise TypeError(f"{field_name} has unsupported union schema")
        return _deserialize_primitive(value, non_none[0], field_name)
    if origin is tuple:
        if not isinstance(value, list):
            raise TypeError(f"{field_name} must be a list in serialized form")
        item_type = get_args(annotation)[0]
        return tuple(
            _deserialize_primitive(item, item_type, field_name) for item in value
        )
    if annotation is datetime:
        return parse_utc_datetime(value, field_name)
    if annotation is timedelta:
        payload = require_exact_fields(value, field_name, ("seconds",))
        return parse_positive_timedelta(payload["seconds"], field_name)
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be an enum string")
        return annotation(value)
    if isinstance(annotation, type) and hasattr(annotation, "from_dict"):
        return annotation.from_dict(value)
    return value
