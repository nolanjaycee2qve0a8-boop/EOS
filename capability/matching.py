"""Immutable boundary for required-to-available capability matching facts."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from capability.descriptor import CapabilityDescriptor
from capability.discovery import AvailableCapabilityCollection


@dataclass(frozen=True, slots=True)
class RequiredCapabilityCollection:
    """Hold exact capability descriptors required by a caller."""

    capabilities: tuple[CapabilityDescriptor, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.capabilities, tuple):
            raise TypeError("capabilities must be a tuple")
        for capability in self.capabilities:
            if not isinstance(capability, CapabilityDescriptor):
                raise TypeError(
                    "capabilities must contain CapabilityDescriptor instances"
                )


@dataclass(frozen=True, slots=True)
class CapabilityMatch:
    """Relate one exact required descriptor to one exact available descriptor."""

    required: CapabilityDescriptor
    available: CapabilityDescriptor

    def __post_init__(self) -> None:
        if not isinstance(self.required, CapabilityDescriptor):
            raise TypeError("required must be a CapabilityDescriptor")
        if not isinstance(self.available, CapabilityDescriptor):
            raise TypeError("available must be a CapabilityDescriptor")


@dataclass(frozen=True, slots=True)
class CapabilityMatchCollection:
    """Hold exact matching facts for required and available collections."""

    required_collection: RequiredCapabilityCollection
    available_collection: AvailableCapabilityCollection
    matches: tuple[CapabilityMatch, ...]
    missing_required: tuple[CapabilityDescriptor, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.required_collection, RequiredCapabilityCollection):
            raise TypeError(
                "required_collection must be a RequiredCapabilityCollection"
            )
        if not isinstance(self.available_collection, AvailableCapabilityCollection):
            raise TypeError(
                "available_collection must be an AvailableCapabilityCollection"
            )
        if not isinstance(self.matches, tuple):
            raise TypeError("matches must be a tuple")
        if not isinstance(self.missing_required, tuple):
            raise TypeError("missing_required must be a tuple")
        for capability_match in self.matches:
            if not isinstance(capability_match, CapabilityMatch):
                raise TypeError("matches must contain CapabilityMatch instances")
            if not any(
                capability_match.required is required
                for required in self.required_collection.capabilities
            ):
                raise ValueError(
                    "match required descriptor must preserve required identity"
                )
            if not any(
                capability_match.available is available
                for available in self.available_collection.capabilities
            ):
                raise ValueError(
                    "match available descriptor must preserve available identity"
                )
        for missing in self.missing_required:
            if not isinstance(missing, CapabilityDescriptor):
                raise TypeError(
                    "missing_required must contain CapabilityDescriptor instances"
                )
            if not any(
                missing is required
                for required in self.required_collection.capabilities
            ):
                raise ValueError(
                    "missing_required descriptor must preserve required identity"
                )
        for required in self.required_collection.capabilities:
            is_matched = any(
                capability_match.required is required
                for capability_match in self.matches
            )
            is_missing = any(missing is required for missing in self.missing_required)
            if is_matched == is_missing:
                raise ValueError(
                    "each required descriptor must belong to exactly one of "
                    "matches or missing_required"
                )


class CapabilityMatchingBoundary(ABC):
    """Define stateless construction of immutable capability matching facts.

    The boundary defines no ranking, scoring, priority, selection,
    optimization, fallback, activation, execution, or intent generation.
    """

    __slots__ = ()

    @abstractmethod
    def match_capabilities(
        self,
        required: RequiredCapabilityCollection,
        available: AvailableCapabilityCollection,
    ) -> CapabilityMatchCollection:
        """Return matching facts without mutating or executing capabilities."""
        raise NotImplementedError
