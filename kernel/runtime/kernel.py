"""Single-tick orchestration boundary for the EOS runtime kernel."""

from dataclasses import dataclass

from kernel.decision import DecisionPipeline
from kernel.domain import Mission, Snapshot
from kernel.event import EventJournal, EventRecord
from kernel.runtime.tick import TickResult
from kernel.runtime.validation import require_instance


@dataclass(frozen=True, slots=True)
class RuntimeKernel:
    """Execute one explicit deterministic tick without owning a loop or clock."""

    pipeline: DecisionPipeline
    journal: EventJournal

    def __post_init__(self) -> None:
        require_instance(self.pipeline, DecisionPipeline, "pipeline")
        require_instance(self.journal, EventJournal, "journal")

    def tick(self, snapshot: Snapshot, mission: Mission) -> TickResult:
        """Execute one decision and append its existing events in order."""
        validated_snapshot = require_instance(snapshot, Snapshot, "snapshot")
        validated_mission = require_instance(mission, Mission, "mission")

        decision_result = self.pipeline.execute(
            validated_snapshot,
            validated_mission,
        )
        records = self.journal.events()
        next_sequence = records[-1].sequence + 1 if records else 0
        progressed_journal = self.journal

        for offset, event in enumerate(decision_result.events):
            progressed_journal = progressed_journal.append(
                EventRecord(sequence=next_sequence + offset, event=event)
            )

        return TickResult(
            decision_result=decision_result,
            journal=progressed_journal,
        )
