"""Focused validation helpers for the event journal boundary."""


def require_sequence(value: object, field_name: str) -> int:
    """Require a non-negative integer sequence that is not a boolean."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an int")
    if value < 0:
        raise ValueError(f"{field_name} must be greater than or equal to 0")
    return value


def require_instance[T](
    value: object,
    expected_type: type[T],
    field_name: str,
) -> T:
    """Require a value to have the specified runtime type."""
    if not isinstance(value, expected_type):
        raise TypeError(f"{field_name} must be an {expected_type.__name__}")
    return value
