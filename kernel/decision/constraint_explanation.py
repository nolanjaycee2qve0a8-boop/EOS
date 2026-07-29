"""Immutable observation of a completed constraint evaluation result."""

from dataclasses import dataclass

from kernel.decision.constraint import FeasibleDecisionIntent
from kernel.decision.intent import DecisionIntent


@dataclass(frozen=True, slots=True)
class ConstraintExplanation:
    """Expose exact source and feasible artifacts without derived reasoning."""

    feasible_intent: FeasibleDecisionIntent
    source_intent: DecisionIntent

    def __post_init__(self) -> None:
        if not isinstance(self.feasible_intent, FeasibleDecisionIntent):
            raise TypeError("feasible_intent must be a FeasibleDecisionIntent")
        if not isinstance(self.source_intent, DecisionIntent):
            raise TypeError("source_intent must be a DecisionIntent")

    @classmethod
    def create(
        cls,
        feasible_intent: FeasibleDecisionIntent,
        source_intent: DecisionIntent,
    ) -> "ConstraintExplanation":
        """Observe exact source and feasible intent references without execution."""
        if not isinstance(feasible_intent, FeasibleDecisionIntent):
            raise TypeError("feasible_intent must be a FeasibleDecisionIntent")
        if not isinstance(source_intent, DecisionIntent):
            raise TypeError("source_intent must be a DecisionIntent")

        return cls(
            feasible_intent=feasible_intent,
            source_intent=source_intent,
        )
