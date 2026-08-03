"""Abstract boundary for describing EMS objectives."""

from abc import ABC, abstractmethod

from objective.model import ObjectiveCollection


class EMSObjectiveBoundary(ABC):
    """Define a stateless extension point for EMS objective descriptions.

    An objective states what the EMS cares about. It does not generate an
    intent, select an action, score alternatives, or decide battery behavior.
    """

    __slots__ = ()

    @abstractmethod
    def describe(self) -> ObjectiveCollection:
        """Return immutable objective descriptions."""
        raise NotImplementedError
