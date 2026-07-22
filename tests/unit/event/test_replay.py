"""Tests for deterministic event journal replay iteration."""

from datetime import UTC, datetime
from typing import cast

import pytest

from kernel.domain import Event
from kernel.event import EventJournal, EventRecord, replay
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


def test_replay_returns_records_in_sequence_order() -> None:
    first = make_record(1)
    second = make_record(3)
    journal = EventJournal().append(first).append(second)
    assert replay(journal) == (first, second)


def test_replay_does_not_mutate_journal() -> None:
    record = make_record(0)
    journal = EventJournal().append(record)
    replay(journal)
    assert journal.events() == (record,)


def test_replay_preserves_event_identity() -> None:
    record = make_record(0)
    replayed = replay(EventJournal().append(record))
    assert replayed[0].event is record.event


def test_replay_preserves_record_identity() -> None:
    record = make_record(0)
    assert replay(EventJournal().append(record))[0] is record


def test_empty_journal_replay() -> None:
    assert replay(EventJournal()) == ()


def test_replay_rejects_invalid_journal() -> None:
    with pytest.raises(TypeError, match="journal"):
        replay(cast(EventJournal, object()))
