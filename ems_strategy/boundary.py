"""Abstract stateless boundary for future EMS strategy implementations."""

from abc import ABC, abstractmethod

from ems_strategy.context import EMSContext
from ems_strategy.decision import EMSDecision


class EMSStrategyBoundary(ABC):
    """Define one strategy evaluation from exact context to exact decision.

    A conforming implementation accepts one ``EMSContext`` and returns one
    ``EMSDecision`` whose ``source_context`` is the exact supplied context.
    Implementations must not mutate, copy, serialize, reconstruct, or retain
    the context. Constraint evaluation, simulation, device access, command
    generation, cache, and history belong outside this boundary.
    """

    __slots__ = ()

    @abstractmethod
    def evaluate(self, context: EMSContext) -> EMSDecision:
        """Return one decision preserving ``decision.source_context is context``."""
        raise NotImplementedError
