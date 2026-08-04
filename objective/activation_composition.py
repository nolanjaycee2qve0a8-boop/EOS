"""Immutable composition of an objective with active capability descriptors."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from capability.activation import ActiveCapabilityCollection
from objective.model import ObjectiveDescriptor


@dataclass(frozen=True, slots=True)
class ObjectiveCapabilityActivationComposition:
    """Relate one exact objective to one complete active capability collection."""

    objective: ObjectiveDescriptor
    active_capabilities: ActiveCapabilityCollection

    def __post_init__(self) -> None:
        if not isinstance(self.objective, ObjectiveDescriptor):
            raise TypeError("objective must be an ObjectiveDescriptor")
        if not isinstance(self.active_capabilities, ActiveCapabilityCollection):
            raise TypeError("active_capabilities must be an ActiveCapabilityCollection")

        capabilities = self.active_capabilities.active_capabilities
        for index, capability in enumerate(capabilities):
            if any(capability is previous for previous in capabilities[:index]):
                raise ValueError(
                    "active_capabilities must not contain duplicate descriptor "
                    "identities"
                )


class ObjectiveCapabilityActivationCompositionBoundary(ABC):
    """Define stateless objective-to-active-capability composition.

    The boundary expresses one complete relationship only. It defines no
    selection, ranking, priority, scoring, optimization, conflict resolution,
    execution, or intent generation.
    """

    __slots__ = ()

    @abstractmethod
    def compose(
        self,
        objective: ObjectiveDescriptor,
        active_capabilities: ActiveCapabilityCollection,
    ) -> ObjectiveCapabilityActivationComposition:
        """Return a relationship preserving both exact input objects."""
        raise NotImplementedError
