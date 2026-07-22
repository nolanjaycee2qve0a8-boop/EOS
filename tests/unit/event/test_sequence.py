"""Tests for immutable EventRecord values."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from kernel.domain import Event
from kernel.event import EventRecord
from kernel.ids import EventId

FIXED_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make_event(number: int = 1) -> Event:
    return Event(
        event_id=EventId(f"event-{number}"),
        event_type="decision_recorded",
        occurred_at=FIXED_TIME,
        recorded_at=FIXED_TIME,
        payload={"number": number},
    )


def test_event_record_creation() -> None:
    event = make_event()
    record = EventRecord(sequence=0, event=event)
    assert record.sequence == 0
    assert record.event is event


def test_event_record_is_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        cast(Any, EventRecord(0, make_event())).sequence = 1


def test_event_record_uses_slots() -> None:
    assert not hasattr(EventRecord(0, make_event()), "__dict__")


@pytest.mark.parametrize("sequence", [-1, -10])
def test_event_record_rejects_negative_sequence(sequence: int) -> None:
    with pytest.raises(ValueError, match="sequence"):
        EventRecord(sequence, make_event())


@pytest.mark.parametrize("sequence", [1.0, "1", None])
def test_event_record_rejects_invalid_sequence_type(sequence: object) -> None:
    with pytest.raises(TypeError, match="sequence"):
        EventRecord(cast(int, sequence), make_event())


@pytest.mark.parametrize("sequence", [True, False])
def test_event_record_rejects_boolean_sequence(sequence: bool) -> None:
    with pytest.raises(TypeError, match="sequence"):
        EventRecord(cast(int, sequence), make_event())


def test_event_record_rejects_invalid_event() -> None:
    with pytest.raises(TypeError, match="event"):
        EventRecord(0, cast(Event, object()))
