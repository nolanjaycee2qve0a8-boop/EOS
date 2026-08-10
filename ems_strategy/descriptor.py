"""Immutable identity descriptor for an EMS strategy."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EMSStrategyDescriptor:
    """Identify a strategy contract without owning its implementation or state."""

    name: str
    version: str

    def __post_init__(self) -> None:
        for field_name in ("name", "version"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a str")
            if not value.strip():
                raise ValueError(f"{field_name} must be non-empty")
