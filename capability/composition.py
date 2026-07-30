"""Abstract boundary for deterministic EMS capability composition."""

from abc import ABC, abstractmethod

from capability.base import EMSCapabilityBoundary
from kernel.decision import DecisionContext, DecisionIntent


class CapabilityCompositionBoundary(ABC):
    """Define ordered, exactly-once capability evaluation.

    The caller-supplied tuple position is the authoritative order. A conforming
    implementation evaluates every tuple position exactly once with the exact
    supplied context and returns the exact resulting intents in the same order.
    It does not select, sort, deduplicate, score, optimize, or resolve intents.
    """

    __slots__ = ()

    @abstractmethod
    def evaluate(
        self,
        context: DecisionContext,
        capabilities: tuple[EMSCapabilityBoundary, ...],
    ) -> tuple[DecisionIntent, ...]:
        """Return one exact intent per capability in caller tuple order."""
        raise NotImplementedError
