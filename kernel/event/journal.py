"""Immutable append-only journal of sequenced domain events."""

from dataclasses import dataclass

from kernel.event.sequence import EventRecord
from kernel.event.validation import require_instance


@dataclass(frozen=True, slots=True, init=False)
class EventJournal:
    """Store EventRecords in deterministic, strictly increasing order."""

    _records: tuple[EventRecord, ...]

    def __init__(self) -> None:
        object.__setattr__(self, "_records", ())

    def append(self, record: EventRecord) -> "EventJournal":
        """Return a new journal with one validated record appended."""
        validated = require_instance(record, EventRecord, "record")
        if any(existing.sequence == validated.sequence for existing in self._records):
            raise ValueError("record.sequence must not duplicate an existing sequence")
        if self._records and validated.sequence < self._records[-1].sequence:
            raise ValueError(
                "record.sequence must be greater than the previous sequence"
            )
        return self._from_records((*self._records, validated))

    def events(self) -> tuple[EventRecord, ...]:
        """Return the journal's immutable records in insertion order."""
        return self._records

    @classmethod
    def _from_records(
        cls,
        records: tuple[EventRecord, ...],
    ) -> "EventJournal":
        journal = cls()
        object.__setattr__(journal, "_records", records)
        return journal
