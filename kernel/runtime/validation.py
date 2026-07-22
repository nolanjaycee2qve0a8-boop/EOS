"""Focused validation helpers for the runtime kernel boundary."""


def require_instance[T](
    value: object,
    expected_type: type[T],
    field_name: str,
) -> T:
    """Require a value to have the specified runtime type."""
    if not isinstance(value, expected_type):
        raise TypeError(f"{field_name} must be a {expected_type.__name__}")
    return value
