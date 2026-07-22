"""Tests for immutable append-only EventJournal behavior."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from kernel.domain import Event
from kernel.event import EventJournal, EventRecord
from kernel.ids import EventId

FIXED_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make_record(sequence: int) -> EventRecord:
    return EventRecord(
        sequence=sequence,
        event=Event(
            event_id=EventId(f"event-{sequence}"),
            event_type="decision_recorded",
            occurred_at=FIXED_TIME,
            recorded_at=FIXED_TIME,
            payload={"sequence": sequence},
        ),
    )


def test_empty_journal() -> None:
    assert EventJournal().events() == ()


def test_append_creates_new_journal() -> None:
    journal = EventJournal()
    appended = journal.append(make_record(0))
    assert appended is not journal


def test_append_leaves_original_journal_unchanged() -> None:
    journal = EventJournal()
    journal.append(make_record(0))
    assert journal.events() == ()


def test_multiple_records_preserve_insertion_order() -> None:
    first = make_record(2)
    second = make_record(5)
    journal = EventJournal().append(first).append(second)
    assert journal.events() == (first, second)


def test_append_preserves_record_identity() -> None:
    record = make_record(0)
    assert EventJournal().append(record).events()[0] is record


def test_duplicate_sequence_is_rejected() -> None:
    journal = EventJournal().append(make_record(1))
    with pytest.raises(ValueError, match=r"record\.sequence"):
        journal.append(make_record(1))


def test_decreasing_sequence_is_rejected() -> None:
    journal = EventJournal().append(make_record(2))
    with pytest.raises(ValueError, match=r"record\.sequence"):
        journal.append(make_record(1))


def test_invalid_record_is_rejected() -> None:
    with pytest.raises(TypeError, match="record"):
        EventJournal().append(cast(EventRecord, object()))


def test_events_returns_immutable_tuple() -> None:
    records = EventJournal().append(make_record(0)).events()
    assert isinstance(records, tuple)
    with pytest.raises(TypeError):
        cast(Any, records)[0] = make_record(1)


def test_journal_is_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        cast(Any, EventJournal())._records = ()


def test_journal_uses_slots() -> None:
    assert not hasattr(EventJournal(), "__dict__")
