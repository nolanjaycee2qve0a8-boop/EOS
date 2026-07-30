"""Immutable observation of an ordered constraint explanation chain."""

from dataclasses import dataclass

from kernel.decision.constraint import FeasibleDecisionIntent
from kernel.decision.intent import DecisionIntent


@dataclass(frozen=True, slots=True)
class ConstraintExplanationEntry:
    """Preserve one completed constraint stage and its caller-supplied reason."""

    source_intent: DecisionIntent
    feasible_intent: FeasibleDecisionIntent
    adjusted: bool
    adjustment_reason: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.source_intent, DecisionIntent):
            raise TypeError("source_intent must be a DecisionIntent")
        if not isinstance(self.feasible_intent, FeasibleDecisionIntent):
            raise TypeError("feasible_intent must be a FeasibleDecisionIntent")
        if not isinstance(self.adjusted, bool):
            raise TypeError("adjusted must be a bool")
        if self.adjustment_reason is not None and not isinstance(
            self.adjustment_reason,
            str,
        ):
            raise TypeError("adjustment_reason must be a str or None")

        identity_adjusted = self.feasible_intent.intent is not self.source_intent
        if self.adjusted is not identity_adjusted:
            raise ValueError("adjusted must match source and feasible intent identity")
        if self.adjusted:
            if self.adjustment_reason is None or not self.adjustment_reason.strip():
                raise ValueError("adjustment_reason must be non-empty when adjusted")
        elif self.adjustment_reason is not None:
            raise ValueError("adjustment_reason must be None when intent is unchanged")

    @classmethod
    def create(
        cls,
        source_intent: DecisionIntent,
        feasible_intent: FeasibleDecisionIntent,
        *,
        adjustment_reason: str | None,
    ) -> "ConstraintExplanationEntry":
        """Record exact artifacts without executing or inferring a reason."""
        if not isinstance(source_intent, DecisionIntent):
            raise TypeError("source_intent must be a DecisionIntent")
        if not isinstance(feasible_intent, FeasibleDecisionIntent):
            raise TypeError("feasible_intent must be a FeasibleDecisionIntent")

        return cls(
            source_intent=source_intent,
            feasible_intent=feasible_intent,
            adjusted=feasible_intent.intent is not source_intent,
            adjustment_reason=adjustment_reason,
        )


@dataclass(frozen=True, slots=True)
class ConstraintExplanationChain:
    """Preserve exact ordered explanations for a completed constraint chain."""

    source_intent: DecisionIntent
    entries: tuple[ConstraintExplanationEntry, ...]
    feasible_intent: FeasibleDecisionIntent

    def __post_init__(self) -> None:
        if not isinstance(self.source_intent, DecisionIntent):
            raise TypeError("source_intent must be a DecisionIntent")
        if not isinstance(self.entries, tuple):
            raise TypeError("entries must be a tuple")
        if not isinstance(self.feasible_intent, FeasibleDecisionIntent):
            raise TypeError("feasible_intent must be a FeasibleDecisionIntent")
        for entry in self.entries:
            if not isinstance(entry, ConstraintExplanationEntry):
                raise TypeError(
                    "entries must contain only ConstraintExplanationEntry instances"
                )

        current_intent = self.source_intent
        for entry in self.entries:
            if entry.source_intent is not current_intent:
                raise ValueError(
                    "each entry must reference the previous exact feasible intent"
                )
            current_intent = entry.feasible_intent.intent

        if self.entries:
            if self.feasible_intent is not self.entries[-1].feasible_intent:
                raise ValueError("feasible_intent must be the exact final entry result")
        elif self.feasible_intent.intent is not self.source_intent:
            raise ValueError("an empty chain must preserve source intent identity")

    @classmethod
    def create(
        cls,
        source_intent: DecisionIntent,
        entries: tuple[ConstraintExplanationEntry, ...],
        feasible_intent: FeasibleDecisionIntent,
    ) -> "ConstraintExplanationChain":
        """Observe an existing completed chain without executing constraints."""
        return cls(
            source_intent=source_intent,
            entries=entries,
            feasible_intent=feasible_intent,
        )
