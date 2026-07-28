"""Stateless constraint boundary for immutable decision intentions."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from kernel.decision.intent import DecisionIntent


@dataclass(frozen=True, slots=True)
class FeasibleDecisionIntent:
    """Reference an intent accepted by a constraint boundary."""

    intent: DecisionIntent

    def __post_init__(self) -> None:
        if not isinstance(self.intent, DecisionIntent):
            raise TypeError("intent must be a DecisionIntent")


class DecisionConstraintBoundary(ABC):
    """Stateless contract for evaluating one immutable DecisionIntent."""

    __slots__ = ()

    @abstractmethod
    def evaluate(self, intent: DecisionIntent) -> FeasibleDecisionIntent:
        """Return a feasible wrapper without mutating the supplied intent."""
        raise NotImplementedError
