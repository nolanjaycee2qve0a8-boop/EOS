"""Immutable output candidate for one Phase 5 decision formation."""

from dataclasses import dataclass

from decision_formation.input import DecisionFormationInput
from decision_formation.intent import DecisionIntent


@dataclass(frozen=True, slots=True)
class DecisionIntentCandidate:
    """Relate one exact formation input to one exact semantic intent."""

    formation_input: DecisionFormationInput
    intent: DecisionIntent

    def __post_init__(self) -> None:
        if not isinstance(self.formation_input, DecisionFormationInput):
            raise TypeError("formation_input must be a DecisionFormationInput")
        if not isinstance(self.intent, DecisionIntent):
            raise TypeError("intent must be a DecisionIntent")
