"""Abstract boundary for resolving candidate EMS decision intents."""

from abc import ABC, abstractmethod

from kernel.decision import DecisionIntent


class IntentResolutionBoundary(ABC):
    """Define the extension point from candidate intents to one intent.

    The boundary declares only the input and output contract. It does not
    define priority, weighting, scoring, ranking, selection, optimization,
    arbitration, merging, or fallback behavior.
    """

    __slots__ = ()

    @abstractmethod
    def resolve(
        self,
        candidates: tuple[DecisionIntent, ...],
    ) -> DecisionIntent:
        """Return one resolved intent under a future explicit strategy."""
        raise NotImplementedError
