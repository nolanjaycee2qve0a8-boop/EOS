"""Abstract grid-side constraint boundary for decision intentions."""

from abc import abstractmethod

from kernel.decision.constraint import (
    DecisionConstraintBoundary,
    FeasibleDecisionIntent,
)
from kernel.decision.intent import DecisionIntent


class GridConstraintBoundary(DecisionConstraintBoundary):
    """Define the stateless extension point for future grid constraints.

    Concrete implementations may receive immutable grid facts through
    construction. This boundary defines no import limit, export limit,
    zero-export, pricing, optimization, forecasting, or device behavior.
    """

    __slots__ = ()

    @abstractmethod
    def evaluate(self, intent: DecisionIntent) -> FeasibleDecisionIntent:
        """Return a feasible intent without mutating the supplied intent."""
        raise NotImplementedError
