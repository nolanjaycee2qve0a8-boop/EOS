"""Immutable observation of one completed EMS strategy decision lineage."""

from dataclasses import dataclass

from ems_strategy.context import EMSContext
from ems_strategy.decision import EMSDecision
from ems_strategy.descriptor import EMSStrategyDescriptor


@dataclass(frozen=True, slots=True)
class DecisionProvenance:
    """Preserve exact context, strategy descriptor, and decision references.

    This artifact observes an already-created ``EMSDecision``. It does not
    execute a strategy, derive a decision, copy an object, or reconstruct
    lineage from serialized values.
    """

    source_context: EMSContext
    source_strategy: EMSStrategyDescriptor
    decision: EMSDecision

    def __post_init__(self) -> None:
        if not isinstance(self.source_context, EMSContext):
            raise TypeError("source_context must be an EMSContext")
        if not isinstance(self.source_strategy, EMSStrategyDescriptor):
            raise TypeError("source_strategy must be an EMSStrategyDescriptor")
        if not isinstance(self.decision, EMSDecision):
            raise TypeError("decision must be an EMSDecision")
        if self.decision.source_context is not self.source_context:
            raise ValueError("decision must preserve exact source_context identity")
        if self.decision.source_strategy is not self.source_strategy:
            raise ValueError("decision must preserve exact source_strategy identity")
