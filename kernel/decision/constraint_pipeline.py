"""Stateless deterministic composition of decision constraints."""

from kernel.decision.constraint import (
    DecisionConstraintBoundary,
    FeasibleDecisionIntent,
)
from kernel.decision.intent import DecisionIntent


class ConstraintEvaluationPipeline:
    """Evaluate caller-supplied constraints in exact tuple order."""

    __slots__ = ()

    @staticmethod
    def evaluate(
        source_intent: DecisionIntent,
        constraints: tuple[DecisionConstraintBoundary, ...],
    ) -> FeasibleDecisionIntent:
        """Return the exact final constraint result without retaining state."""
        if not isinstance(source_intent, DecisionIntent):
            raise TypeError("source_intent must be a DecisionIntent")
        if not isinstance(constraints, tuple):
            raise TypeError("constraints must be a tuple")
        for constraint in constraints:
            if not isinstance(constraint, DecisionConstraintBoundary):
                raise TypeError(
                    "constraints must contain only DecisionConstraintBoundary instances"
                )

        current_intent = source_intent
        final_result: FeasibleDecisionIntent | None = None

        for constraint in constraints:
            result = constraint.evaluate(current_intent)
            if not isinstance(result, FeasibleDecisionIntent):
                raise TypeError("constraint must return a FeasibleDecisionIntent")
            final_result = result
            current_intent = result.intent

        if final_result is None:
            return FeasibleDecisionIntent(intent=source_intent)
        return final_result
