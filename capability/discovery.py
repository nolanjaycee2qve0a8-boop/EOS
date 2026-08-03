"""Immutable boundary for discovering available capability descriptors."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from capability.descriptor import CapabilityDescriptor


@dataclass(frozen=True, slots=True)
class AvailableCapabilityCollection:
    """Hold exact descriptors reported as available by a discovery provider."""

    capabilities: tuple[CapabilityDescriptor, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.capabilities, tuple):
            raise TypeError("capabilities must be a tuple")
        for capability in self.capabilities:
            if not isinstance(capability, CapabilityDescriptor):
                raise TypeError(
                    "capabilities must contain CapabilityDescriptor instances"
                )


class CapabilityDiscoveryBoundary(ABC):
    """Define stateless discovery of available capability descriptors.

    The boundary reports descriptor relationships only. It does not connect to
    devices, inspect protocols, instantiate capabilities, match, select,
    activate, execute, or generate intents.
    """

    __slots__ = ()

    @abstractmethod
    def discover(self) -> AvailableCapabilityCollection:
        """Return immutable references to available capability descriptors."""
        raise NotImplementedError
