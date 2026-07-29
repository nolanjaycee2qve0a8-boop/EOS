"""Immutable lifecycle observation for one decision evaluation cycle."""

from dataclasses import dataclass

from kernel.decision.constraint import FeasibleDecisionIntent
from kernel.decision.constraint_explanation import ConstraintExplanation
from kernel.decision.context import DecisionContext
from kernel.decision.context_result import DecisionContextResult
from kernel.decision.intent import DecisionIntent


@dataclass(frozen=True, slots=True)
class DecisionEvaluationCycle:
    """Preserve exact artifacts from one completed decision evaluation."""

    context: DecisionContext
    result: DecisionContextResult
    source_intent: DecisionIntent
    feasible_intent: FeasibleDecisionIntent
    explanation: ConstraintExplanation

    def __post_init__(self) -> None:
        if not isinstance(self.context, DecisionContext):
            raise TypeError("context must be a DecisionContext")
        if not isinstance(self.result, DecisionContextResult):
            raise TypeError("result must be a DecisionContextResult")
        if not isinstance(self.source_intent, DecisionIntent):
            raise TypeError("source_intent must be a DecisionIntent")
        if not isinstance(self.feasible_intent, FeasibleDecisionIntent):
            raise TypeError("feasible_intent must be a FeasibleDecisionIntent")
        if not isinstance(self.explanation, ConstraintExplanation):
            raise TypeError("explanation must be a ConstraintExplanation")

        if self.source_intent is not self.result.intent:
            raise ValueError("source_intent must be the exact result intent")
        if self.explanation.feasible_intent is not self.feasible_intent:
            raise ValueError("explanation must reference the exact feasible_intent")
        if self.explanation.source_intent is not self.source_intent:
            raise ValueError("explanation must reference the exact source intent")

    @classmethod
    def create(
        cls,
        context: DecisionContext,
        result: DecisionContextResult,
        feasible_intent: FeasibleDecisionIntent,
        explanation: ConstraintExplanation,
    ) -> "DecisionEvaluationCycle":
        """Observe existing lifecycle artifacts without executing any stage."""
        return cls(
            context=context,
            result=result,
            source_intent=result.intent,
            feasible_intent=feasible_intent,
            explanation=explanation,
        )
