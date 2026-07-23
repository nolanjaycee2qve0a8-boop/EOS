"""Immutable output from one deterministic runtime tick."""

from dataclasses import dataclass

from kernel.decision import DecisionResult
from kernel.event import EventJournal
from kernel.runtime.validation import require_instance


@dataclass(frozen=True, slots=True)
class TickResult:
    """Carry the exact decision result and progressed immutable journal."""

    decision_result: DecisionResult
    journal: EventJournal

    def __post_init__(self) -> None:
        require_instance(
            self.decision_result,
            DecisionResult,
            "decision_result",
        )
        require_instance(self.journal, EventJournal, "journal")
