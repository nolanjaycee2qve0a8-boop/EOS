"""Immutable descriptor contract for an EMS capability."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CapabilityDescriptor:
    """Describe a capability without referencing its implementation."""

    name: str
    description: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError("name must be a str")
        if not self.name.strip():
            raise ValueError("name must be non-empty")
        if not isinstance(self.description, str):
            raise TypeError("description must be a str")
        if not self.description.strip():
            raise ValueError("description must be non-empty")
