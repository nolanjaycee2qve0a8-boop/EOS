"""Immutable boundary for activating matched capability descriptors."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from capability.descriptor import CapabilityDescriptor
from capability.matching import CapabilityMatchCollection


@dataclass(frozen=True, slots=True)
class ActiveCapabilityCollection:
    """Record active and inactive states for exact matched descriptors."""

    source_collection: CapabilityMatchCollection
    active_capabilities: tuple[CapabilityDescriptor, ...]
    inactive_capabilities: tuple[CapabilityDescriptor, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_collection, CapabilityMatchCollection):
            raise TypeError("source_collection must be a CapabilityMatchCollection")
        if not isinstance(self.active_capabilities, tuple):
            raise TypeError("active_capabilities must be a tuple")
        if not isinstance(self.inactive_capabilities, tuple):
            raise TypeError("inactive_capabilities must be a tuple")

        matched_capabilities = tuple(
            capability_match.available
            for capability_match in self.source_collection.matches
        )
        for field_name, capabilities in (
            ("active_capabilities", self.active_capabilities),
            ("inactive_capabilities", self.inactive_capabilities),
        ):
            for capability in capabilities:
                if not isinstance(capability, CapabilityDescriptor):
                    raise TypeError(
                        f"{field_name} must contain CapabilityDescriptor instances"
                    )
                if not any(capability is matched for matched in matched_capabilities):
                    raise ValueError(
                        f"{field_name} must preserve matched descriptor identity"
                    )

        for matched in matched_capabilities:
            is_active = any(
                capability is matched for capability in self.active_capabilities
            )
            is_inactive = any(
                capability is matched for capability in self.inactive_capabilities
            )
            if is_active == is_inactive:
                raise ValueError(
                    "each matched descriptor must belong to exactly one of "
                    "active_capabilities or inactive_capabilities"
                )


class CapabilityActivationBoundary(ABC):
    """Define stateless activation status for matched capability descriptors.

    The boundary defines no priority, ranking, scoring, selection,
    optimization, conflict resolution, fallback, execution, or intent
    generation.
    """

    __slots__ = ()

    @abstractmethod
    def activate(
        self,
        matches: CapabilityMatchCollection,
    ) -> ActiveCapabilityCollection:
        """Return immutable activation states without mutating match facts."""
        raise NotImplementedError
