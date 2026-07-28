"""Abstract boundary for policies consuming immutable DecisionContext."""

from abc import ABC, abstractmethod

from kernel.decision import DecisionContext, DecisionContextResult


class DecisionContextPolicy(ABC):
    """Stateless contract from DecisionContext to DecisionContextResult."""

    __slots__ = ()

    @abstractmethod
    def evaluate(self, context: DecisionContext) -> DecisionContextResult:
        """Return a DecisionContextResult without mutating the input."""
        raise NotImplementedError
