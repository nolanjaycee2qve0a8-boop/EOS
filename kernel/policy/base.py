"""Abstract boundary for future deterministic EMS policies."""

from abc import ABC, abstractmethod

from kernel.context import EnergySystemContext
from kernel.decision import DecisionResult


class EMSPolicy(ABC):
    """Stateless, side-effect-free contract for deterministic EMS decisions."""

    __slots__ = ()

    @abstractmethod
    def evaluate(self, context: EnergySystemContext) -> DecisionResult:
        """Return a DecisionResult without mutating the immutable context."""
        raise NotImplementedError
