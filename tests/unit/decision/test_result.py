"""Tests for immutable DecisionResult values."""

from collections.abc import Iterable
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from kernel.decision import DecisionResult
from kernel.domain import Command, Event
from kernel.ids import (
    AssetId,
    CommandId,
    EventId,
    MissionId,
    SnapshotId,
)

FIXED_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make_command(number: int) -> Command:
    return Command(
        command_id=CommandId(f"command-{number}"),
        mission_id=MissionId("mission-1"),
        snapshot_id=SnapshotId("snapshot-1"),
        asset_id=AssetId("asset-1"),
        issued_at=FIXED_TIME,
        action="set_power",
        parameters={"power_kw": number},
    )


def make_event(number: int) -> Event:
    return Event(
        event_id=EventId(f"event-{number}"),
        event_type="command_issued",
        occurred_at=FIXED_TIME,
        recorded_at=FIXED_TIME,
        payload={"sequence": number},
    )


def test_result_can_be_empty() -> None:
    result = DecisionResult()
    assert result.commands == ()
    assert result.events == ()


def test_result_stores_commands_as_tuple() -> None:
    result = DecisionResult(commands=[make_command(1)])
    assert isinstance(result.commands, tuple)


def test_result_stores_events_as_tuple() -> None:
    result = DecisionResult(events=[make_event(1)])
    assert isinstance(result.events, tuple)


def test_result_defensively_copies_input_lists() -> None:
    commands = [make_command(1)]
    events = [make_event(1)]
    result = DecisionResult(commands, events)
    commands.append(make_command(2))
    events.append(make_event(2))
    assert len(result.commands) == 1
    assert len(result.events) == 1


def test_result_accepts_generators() -> None:
    result = DecisionResult(
        (make_command(number) for number in (1, 2)),
        (make_event(number) for number in (1, 2)),
    )
    assert len(result.commands) == 2
    assert len(result.events) == 2


def test_result_rejects_invalid_command_elements() -> None:
    commands = cast(Iterable[Command], [make_command(1), object()])
    with pytest.raises(TypeError, match="commands"):
        DecisionResult(commands=commands)


def test_result_rejects_invalid_event_elements() -> None:
    events = cast(Iterable[Event], [make_event(1), object()])
    with pytest.raises(TypeError, match="events"):
        DecisionResult(events=events)


@pytest.mark.parametrize("value", ["commands", b"commands", {"command": 1}])
def test_result_rejects_inappropriate_command_iterables(value: object) -> None:
    commands = cast(Iterable[Command], value)
    with pytest.raises(TypeError, match="commands"):
        DecisionResult(commands=commands)


@pytest.mark.parametrize("value", ["events", b"events", {"event": 1}])
def test_result_rejects_inappropriate_event_iterables(value: object) -> None:
    events = cast(Iterable[Event], value)
    with pytest.raises(TypeError, match="events"):
        DecisionResult(events=events)


def test_result_is_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        cast(Any, DecisionResult.empty()).commands = ()


def test_result_uses_slots() -> None:
    assert not hasattr(DecisionResult.empty(), "__dict__")


def test_result_supports_value_equality() -> None:
    assert DecisionResult([make_command(1)], [make_event(1)]) == DecisionResult(
        [make_command(1)], [make_event(1)]
    )


def test_result_preserves_input_order() -> None:
    command_1, command_2 = make_command(1), make_command(2)
    event_1, event_2 = make_event(1), make_event(2)
    result = DecisionResult([command_2, command_1], [event_2, event_1])
    assert result.commands == (command_2, command_1)
    assert result.events == (event_2, event_1)


def test_empty_returns_valid_independent_results() -> None:
    first = DecisionResult.empty()
    second = DecisionResult.empty()
    assert first == second
    assert first is not second
