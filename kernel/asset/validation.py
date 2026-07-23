"""Focused validation helpers for immutable energy assets."""


def require_non_empty_string(value: object, field_name: str) -> str:
    """Require a string containing non-whitespace text."""
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def require_positive_number(value: object, field_name: str) -> float:
    """Require a non-boolean numeric value greater than zero."""
    normalized = _require_number(value, field_name)
    if not normalized > 0:
        raise ValueError(f"{field_name} must be greater than 0")
    return normalized


def require_non_negative_number(value: object, field_name: str) -> float:
    """Require a non-boolean numeric value greater than or equal to zero."""
    normalized = _require_number(value, field_name)
    if not normalized >= 0:
        raise ValueError(f"{field_name} must be greater than or equal to 0")
    return normalized


def _require_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    return float(value)
