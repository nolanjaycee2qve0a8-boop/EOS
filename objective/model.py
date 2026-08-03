"""Immutable data contracts for EMS objective descriptions."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ObjectiveDescriptor:
    """Describe one concern of the EMS without decision semantics."""

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


@dataclass(frozen=True, slots=True)
class ObjectiveCollection:
    """Hold objective descriptors in exact caller-supplied tuple order."""

    objectives: tuple[ObjectiveDescriptor, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.objectives, tuple):
            raise TypeError("objectives must be a tuple")
        for objective in self.objectives:
            if not isinstance(objective, ObjectiveDescriptor):
                raise TypeError("objectives must contain ObjectiveDescriptor instances")
