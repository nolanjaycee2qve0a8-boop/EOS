"""Immutable association between one EMS cycle and its progressed journal."""

from dataclasses import dataclass
from functools import reduce

from kernel.cycle.cycle import EMSCycle
from kernel.event import EventJournal, EventRecord


@dataclass(frozen=True, slots=True)
class JournaledEMSCycle:
    """Pair an exact completed cycle with its deterministically progressed journal."""

    cycle: EMSCycle
    journal: EventJournal

    def __post_init__(self) -> None:
        if not isinstance(self.cycle, EMSCycle):
            raise TypeError("cycle must be an EMSCycle")
        if not isinstance(self.journal, EventJournal):
            raise TypeError("journal must be an EventJournal")

    @classmethod
    def record(
        cls,
        cycle: EMSCycle,
        journal: EventJournal,
    ) -> "JournaledEMSCycle":
        """Append the cycle's events in order and return their immutable association."""
        if not isinstance(cycle, EMSCycle):
            raise TypeError("cycle must be an EMSCycle")
        if not isinstance(journal, EventJournal):
            raise TypeError("journal must be an EventJournal")

        events = cycle.result.events
        if not events:
            return cls(cycle=cycle, journal=journal)

        existing_records = journal.events()
        first_sequence = (
            0 if not existing_records else existing_records[-1].sequence + 1
        )
        new_records = (
            EventRecord(sequence=first_sequence + offset, event=event)
            for offset, event in enumerate(events)
        )
        progressed_journal = reduce(EventJournal.append, new_records, journal)
        return cls(cycle=cycle, journal=progressed_journal)
