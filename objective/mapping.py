"""Immutable boundary for objective-to-capability descriptor mappings."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from capability.descriptor import CapabilityDescriptor
from objective.activation import ActiveObjectiveCollection
from objective.model import ObjectiveCollection, ObjectiveDescriptor


@dataclass(frozen=True, slots=True)
class ObjectiveCapabilityMapping:
    """Relate one exact objective descriptor to capability descriptors."""

    objective: ObjectiveDescriptor
    capabilities: tuple[CapabilityDescriptor, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.objective, ObjectiveDescriptor):
            raise TypeError("objective must be an ObjectiveDescriptor")
        if not isinstance(self.capabilities, tuple):
            raise TypeError("capabilities must be a tuple")
        for capability in self.capabilities:
            if not isinstance(capability, CapabilityDescriptor):
                raise TypeError(
                    "capabilities must contain CapabilityDescriptor instances"
                )


@dataclass(frozen=True, slots=True)
class ObjectiveCapabilityMappingCollection:
    """Hold mappings for one exact objective collection source."""

    source_collection: ObjectiveCollection | ActiveObjectiveCollection
    mappings: tuple[ObjectiveCapabilityMapping, ...]

    def __post_init__(self) -> None:
        source_objectives = self._source_objectives()
        if not isinstance(self.mappings, tuple):
            raise TypeError("mappings must be a tuple")
        for mapping in self.mappings:
            if not isinstance(mapping, ObjectiveCapabilityMapping):
                raise TypeError(
                    "mappings must contain ObjectiveCapabilityMapping instances"
                )
            if not any(
                mapping.objective is source_objective
                for source_objective in source_objectives
            ):
                raise ValueError(
                    "mapping objective must preserve source descriptor identity"
                )

    def _source_objectives(self) -> tuple[ObjectiveDescriptor, ...]:
        if isinstance(self.source_collection, ObjectiveCollection):
            return self.source_collection.objectives
        if isinstance(self.source_collection, ActiveObjectiveCollection):
            return self.source_collection.active_objectives
        raise TypeError(
            "source_collection must be an ObjectiveCollection or "
            "ActiveObjectiveCollection"
        )


class ObjectiveCapabilityMappingBoundary(ABC):
    """Define stateless objective-to-capability descriptor mapping.

    The boundary expresses relationships only. It does not select, rank,
    prioritize, score, weight, optimize, execute, or generate intents.
    """

    __slots__ = ()

    @abstractmethod
    def map_objectives(
        self,
        objectives: ObjectiveCollection | ActiveObjectiveCollection,
    ) -> ObjectiveCapabilityMappingCollection:
        """Return immutable descriptor relationships for the exact source."""
        raise NotImplementedError
