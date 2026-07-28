"""Abstract boundary for policies consuming immutable DecisionContext."""

from abc import ABC, abstractmethod

from kernel.decision import DecisionContext, DecisionResult


class DecisionContextPolicy(ABC):
    """Stateless contract from DecisionContext to DecisionResult."""

    __slots__ = ()

    @abstractmethod
    def evaluate(self, context: DecisionContext) -> DecisionResult:
        """Return a DecisionResult without mutating the DecisionContext."""
        raise NotImplementedError
