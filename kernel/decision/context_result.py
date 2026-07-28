"""Immutable output boundary for DecisionContext policies."""

from dataclasses import dataclass

from kernel.decision.intent import DecisionIntent


@dataclass(frozen=True, slots=True)
class DecisionContextResult:
    """Represent policy output before future command generation.

    The result preserves one semantic DecisionIntent. Device commands and
    execution events belong to later architecture layers.
    """

    intent: DecisionIntent

    def __post_init__(self) -> None:
        if not isinstance(self.intent, DecisionIntent):
            raise TypeError("intent must be a DecisionIntent")
