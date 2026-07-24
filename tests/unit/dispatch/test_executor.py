"""Tests for deterministic sequential command execution."""

from collections.abc import Callable
from datetime import UTC, datetime
from inspect import signature
from typing import Any, cast

import pytest

from kernel.decision import DecisionResult
from kernel.dispatch import CommandDispatcher, CommandExecutor
from kernel.domain import Command, Event
from kernel.ids import AssetId, CommandId, EventId, MissionId, SnapshotId

FIXED_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
DISPATCH_ERROR = RuntimeError("dispatch failed")


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


def make_event() -> Event:
    return Event(
        event_id=EventId("event-1"),
        event_type="decision_recorded",
        occurred_at=FIXED_TIME,
        recorded_at=FIXED_TIME,
        payload={},
    )


def execute_as_object(
    dispatcher: CommandDispatcher,
    decision_result: DecisionResult,
) -> object:
    executable = cast(
        Callable[[CommandDispatcher, DecisionResult], object],
        CommandExecutor.execute,
    )
    return executable(dispatcher, decision_result)


class RecordingDispatcher(CommandDispatcher):
    """Test-only dispatcher recording exact call order and identities."""

    __slots__ = ("commands",)

    def __init__(self) -> None:
        self.commands: list[Command] = []

    def dispatch(self, command: Command) -> None:
        self.commands.append(command)


class FailingDispatcher(CommandDispatcher):
    """Test-only dispatcher raising at one zero-based call position."""

    __slots__ = ("attempts", "fail_at")

    def __init__(self, fail_at: int) -> None:
        self.attempts: list[Command] = []
        self.fail_at = fail_at

    def dispatch(self, command: Command) -> None:
        self.attempts.append(command)
        if len(self.attempts) - 1 == self.fail_at:
            raise DISPATCH_ERROR


class DuckDispatcher:
    """Invalid test probe that resembles but does not implement the boundary."""

    __slots__ = ("commands",)

    def __init__(self) -> None:
        self.commands: list[Command] = []

    def dispatch(self, command: Command) -> None:
        self.commands.append(command)


def test_one_command_dispatches_exactly_once_and_returns_none() -> None:
    dispatcher = RecordingDispatcher()
    command = make_command(1)

    result = execute_as_object(
        dispatcher,
        DecisionResult(commands=(command,)),
    )

    assert result is None
    assert dispatcher.commands == [command]
    assert dispatcher.commands[0] is command


def test_multiple_commands_dispatch_once_per_position_in_exact_order() -> None:
    dispatcher = RecordingDispatcher()
    commands = (make_command(1), make_command(2), make_command(3))

    CommandExecutor.execute(
        dispatcher,
        DecisionResult(commands=commands),
    )

    assert len(dispatcher.commands) == len(commands)
    assert all(
        actual is expected
        for actual, expected in zip(dispatcher.commands, commands, strict=True)
    )


def test_duplicate_references_dispatch_for_every_tuple_position() -> None:
    dispatcher = RecordingDispatcher()
    command = make_command(1)

    CommandExecutor.execute(
        dispatcher,
        DecisionResult(commands=(command, command, command)),
    )

    assert len(dispatcher.commands) == 3
    assert all(dispatched is command for dispatched in dispatcher.commands)


def test_empty_commands_make_no_calls_and_return_none() -> None:
    dispatcher = RecordingDispatcher()

    result = execute_as_object(dispatcher, DecisionResult.empty())

    assert result is None
    assert dispatcher.commands == []


@pytest.mark.parametrize(
    ("fail_at", "expected_attempt_count"),
    [
        (0, 1),
        (1, 2),
        (2, 3),
    ],
)
def test_failure_stops_immediately_without_retry(
    fail_at: int,
    expected_attempt_count: int,
) -> None:
    commands = (make_command(1), make_command(2), make_command(3))
    dispatcher = FailingDispatcher(fail_at)

    with pytest.raises(RuntimeError) as raised:
        CommandExecutor.execute(
            dispatcher,
            DecisionResult(commands=commands),
        )

    assert raised.value is DISPATCH_ERROR
    assert len(dispatcher.attempts) == expected_attempt_count
    assert all(
        actual is expected
        for actual, expected in zip(
            dispatcher.attempts,
            commands[:expected_attempt_count],
            strict=True,
        )
    )
    assert dispatcher.attempts.count(commands[fail_at]) == 1


def test_decision_result_events_are_ignored() -> None:
    dispatcher = RecordingDispatcher()
    event = make_event()

    CommandExecutor.execute(
        dispatcher,
        DecisionResult(events=(event,)),
    )

    assert dispatcher.commands == []


def test_invalid_dispatcher_fails_before_duck_dispatch() -> None:
    probe = DuckDispatcher()

    with pytest.raises(TypeError, match="dispatcher"):
        CommandExecutor.execute(
            cast(CommandDispatcher, probe),
            DecisionResult(commands=(make_command(1),)),
        )

    assert probe.commands == []


def test_invalid_decision_result_fails_before_any_dispatch() -> None:
    dispatcher = RecordingDispatcher()

    with pytest.raises(TypeError, match="decision_result"):
        CommandExecutor.execute(
            dispatcher,
            cast(DecisionResult, object()),
        )

    assert dispatcher.commands == []


def test_executor_is_stateless_and_has_no_instance_dictionary() -> None:
    executor = CommandExecutor()

    assert CommandExecutor.__slots__ == ()
    assert not hasattr(executor, "__dict__")
    with pytest.raises(AttributeError):
        cast(Any, executor).dispatcher = RecordingDispatcher()


def test_execute_signature_and_return_annotation() -> None:
    execute_signature = signature(CommandExecutor.execute)

    assert list(execute_signature.parameters) == [
        "dispatcher",
        "decision_result",
    ]
    assert execute_signature.return_annotation is None
