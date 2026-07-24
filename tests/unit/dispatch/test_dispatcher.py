"""Tests for the abstract command dispatcher contract."""

from abc import ABC
from datetime import UTC, datetime
from inspect import isabstract, signature
from typing import get_type_hints

import pytest

from kernel.dispatch import CommandDispatcher
from kernel.domain import Command
from kernel.ids import AssetId, CommandId, MissionId, SnapshotId

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


class RecordingDispatcher(CommandDispatcher):
    """Minimal test-only dispatcher that records exact supplied commands."""

    __slots__ = ("commands",)

    def __init__(self) -> None:
        self.commands: list[Command] = []

    def dispatch(self, command: Command) -> None:
        self.commands.append(command)


class RaisingDispatcher(CommandDispatcher):
    """Test-only dispatcher that raises one stable exception."""

    __slots__ = ()

    def dispatch(self, command: Command) -> None:
        raise DISPATCH_ERROR


def test_dispatcher_is_abstract_interface() -> None:
    assert issubclass(CommandDispatcher, ABC)
    assert isabstract(CommandDispatcher)
    assert getattr(CommandDispatcher.dispatch, "__isabstractmethod__", False)


def test_dispatcher_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        CommandDispatcher()  # type: ignore[abstract]


def test_minimal_valid_subclass_can_be_instantiated() -> None:
    assert isinstance(RecordingDispatcher(), CommandDispatcher)


def test_dispatch_receives_exact_command_without_copy_or_transformation() -> None:
    dispatcher = RecordingDispatcher()
    command = make_command(1)

    dispatcher.dispatch(command)

    assert dispatcher.commands == [command]
    assert dispatcher.commands[0] is command


def test_different_command_objects_may_be_dispatched() -> None:
    dispatcher = RecordingDispatcher()
    first = make_command(1)
    second = make_command(2)

    dispatcher.dispatch(first)
    dispatcher.dispatch(second)

    assert dispatcher.commands[0] is first
    assert dispatcher.commands[1] is second


def test_implementation_exception_identity_propagates() -> None:
    with pytest.raises(RuntimeError) as raised:
        RaisingDispatcher().dispatch(make_command(1))

    assert raised.value is DISPATCH_ERROR


def test_boundary_has_empty_slots_and_no_instance_dictionary() -> None:
    dispatcher = RecordingDispatcher()

    assert CommandDispatcher.__slots__ == ()
    assert not hasattr(dispatcher, "__dict__")


def test_dispatch_signature_contains_only_self_and_command() -> None:
    assert list(signature(CommandDispatcher.dispatch).parameters) == [
        "self",
        "command",
    ]


def test_dispatch_contract_uses_command_and_returns_none() -> None:
    hints = get_type_hints(CommandDispatcher.dispatch)

    assert hints["command"] is Command
    assert hints["return"] is type(None)
    assert signature(CommandDispatcher.dispatch).return_annotation is None
