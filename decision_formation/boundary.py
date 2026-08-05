"""Abstract boundary for Phase 5 decision formation."""

from abc import ABC, abstractmethod

from decision_formation.candidate import DecisionIntentCandidate
from decision_formation.input import DecisionFormationInput


class DecisionFormationBoundary(ABC):
    """Define a stateless extension point for forming one intent candidate."""

    __slots__ = ()

    @abstractmethod
    def form(
        self,
        formation_input: DecisionFormationInput,
    ) -> DecisionIntentCandidate:
        """Return one candidate without mutating or executing source evidence."""
        raise NotImplementedError
