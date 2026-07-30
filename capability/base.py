"""Abstract boundary for EMS business capabilities."""

from abc import ABC, abstractmethod

from kernel.decision import DecisionContext, DecisionIntent


class EMSCapabilityBoundary(ABC):
    """Define a stateless extension point from decision facts to intent.

    A capability expresses what a business objective wants the energy system
    to do. Physical feasibility, execution, and device control belong to
    separate EOS boundaries.
    """

    __slots__ = ()

    @abstractmethod
    def evaluate(self, context: DecisionContext) -> DecisionIntent:
        """Return one semantic intent without mutating the supplied context."""
        raise NotImplementedError
