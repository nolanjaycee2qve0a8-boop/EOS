"""Immutable boundary for activating described EMS objectives."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from objective.model import ObjectiveCollection, ObjectiveDescriptor


@dataclass(frozen=True, slots=True)
class ActiveObjectiveCollection:
    """Reference active descriptors from one exact source collection."""

    source_collection: ObjectiveCollection
    active_objectives: tuple[ObjectiveDescriptor, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_collection, ObjectiveCollection):
            raise TypeError("source_collection must be an ObjectiveCollection")
        if not isinstance(self.active_objectives, tuple):
            raise TypeError("active_objectives must be a tuple")
        for objective in self.active_objectives:
            if not isinstance(objective, ObjectiveDescriptor):
                raise TypeError(
                    "active_objectives must contain ObjectiveDescriptor instances"
                )
            if not any(
                objective is source_objective
                for source_objective in self.source_collection.objectives
            ):
                raise ValueError(
                    "active_objectives must preserve source descriptor identity"
                )


class ObjectiveActivationBoundary(ABC):
    """Define stateless activation of immutable objective descriptions.

    A conforming implementation receives one exact ObjectiveCollection per
    call and returns one immutable ActiveObjectiveCollection. The boundary
    defines no priority, ranking, conflict resolution, weighting, scoring,
    optimization, or intent generation.
    """

    __slots__ = ()

    @abstractmethod
    def activate(
        self,
        objectives: ObjectiveCollection,
    ) -> ActiveObjectiveCollection:
        """Return active objective references without mutating the source."""
        raise NotImplementedError
