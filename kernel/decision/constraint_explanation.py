"""Immutable observation of a completed constraint evaluation result."""

from dataclasses import dataclass

from kernel.decision.constraint import FeasibleDecisionIntent
from kernel.decision.intent import DecisionIntent


@dataclass(frozen=True, slots=True)
class ConstraintExplanation:
    """Expose exact constraint artifacts without deriving new reasoning."""

    feasible_intent: FeasibleDecisionIntent
    source_intent: DecisionIntent

    def __post_init__(self) -> None:
        if not isinstance(self.feasible_intent, FeasibleDecisionIntent):
            raise TypeError("feasible_intent must be a FeasibleDecisionIntent")
        if not isinstance(self.source_intent, DecisionIntent):
            raise TypeError("source_intent must be a DecisionIntent")
        if self.source_intent is not self.feasible_intent.intent:
            raise ValueError("source_intent must be the exact feasible intent source")

    @classmethod
    def create(
        cls,
        feasible_intent: FeasibleDecisionIntent,
    ) -> "ConstraintExplanation":
        """Observe an existing feasible intent without recomputing it."""
        if not isinstance(feasible_intent, FeasibleDecisionIntent):
            raise TypeError("feasible_intent must be a FeasibleDecisionIntent")

        return cls(
            feasible_intent=feasible_intent,
            source_intent=feasible_intent.intent,
        )
