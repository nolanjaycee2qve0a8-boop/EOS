"""Tests for Event."""

from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest

from kernel.domain import Event
from kernel.ids import CausationId, CorrelationId, EventId

FIXED_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
EVENT_ID = EventId("event-1")


def make_event(
    *,
    event_id: EventId = EVENT_ID,
    event_type: str = "command_issued",
    occurred_at: datetime = FIXED_TIME,
    recorded_at: datetime = FIXED_TIME,
    payload: Mapping[str, object] | None = None,
    correlation_id: CorrelationId | None = None,
    causation_id: CausationId | None = None,
) -> Event:
    return Event(
        event_id=event_id,
        event_type=event_type,
        occurred_at=occurred_at,
        recorded_at=recorded_at,
        payload={} if payload is None else payload,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )


def test_event_creation() -> None:
    event = make_event(correlation_id=CorrelationId("correlation-1"))
    assert event.event_type == "command_issued"


def test_event_fields_are_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        cast(Any, make_event()).event_type = "changed"


@pytest.mark.parametrize(
    ("field_name", "factory"),
    [
        (
            "occurred_at",
            lambda: make_event(occurred_at=datetime(2026, 1, 1, 12, 0)),
        ),
        (
            "recorded_at",
            lambda: make_event(recorded_at=datetime(2026, 1, 1, 12, 0)),
        ),
    ],
)
def test_event_rejects_naive_times(
    field_name: str, factory: Callable[[], Event]
) -> None:
    with pytest.raises(ValueError, match=field_name):
        factory()


def test_event_rejects_empty_id() -> None:
    with pytest.raises(ValueError, match="event_id"):
        make_event(event_id=EventId(" "))


@pytest.mark.parametrize("event_type", ["", "  "])
def test_event_rejects_empty_type(event_type: str) -> None:
    with pytest.raises(ValueError, match="event_type"):
        make_event(event_type=event_type)


def test_event_rejects_recorded_at_before_occurred_at() -> None:
    with pytest.raises(ValueError, match="recorded_at"):
        make_event(recorded_at=FIXED_TIME - timedelta(microseconds=1))


def test_event_allows_equal_times() -> None:
    assert make_event().recorded_at == make_event().occurred_at


@pytest.mark.parametrize(
    ("field_name", "factory"),
    [
        (
            "correlation_id",
            lambda: make_event(correlation_id=CorrelationId("")),
        ),
        ("causation_id", lambda: make_event(causation_id=CausationId(" "))),
    ],
)
def test_event_rejects_empty_optional_ids(
    field_name: str, factory: Callable[[], Event]
) -> None:
    with pytest.raises(ValueError, match=field_name):
        factory()


def test_event_defensively_copies_payload() -> None:
    payload: dict[str, object] = {"command_id": "command-1"}
    event = make_event(payload=payload)
    payload["command_id"] = "command-2"
    assert event.payload["command_id"] == "command-1"


def test_event_payload_is_read_only() -> None:
    payload = cast(MutableMapping[str, object], make_event().payload)
    with pytest.raises(TypeError):
        payload["command_id"] = "command-1"


def test_event_value_equality() -> None:
    assert make_event(payload={"command_id": "command-1"}) == make_event(
        payload={"command_id": "command-1"}
    )
