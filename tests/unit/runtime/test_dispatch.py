"""Tests for explicit dispatch of an existing journaled EMS tick."""

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from inspect import signature
from typing import Any, cast

import pytest

import kernel.runtime.journaled as journaled_module
from kernel.context import EnergySystemContext
from kernel.cycle import EMSCycle, JournaledEMSCycle
from kernel.decision import DecisionResult
from kernel.dispatch import CommandDispatcher, CommandExecutor
from kernel.domain import Command, Event
from kernel.event import EventJournal
from kernel.ids import (
    AssetId,
    CommandId,
    EventId,
    MissionId,
    SnapshotId,
)
from kernel.policy import EMSPolicy
from kernel.power import PowerFlow
from kernel.runtime import (
    DispatchedJournaledEMSTick,
    JournaledEMSRuntime,
    JournaledEMSTick,
)

FIXED_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
DISPATCH_ERROR = RuntimeError("dispatch failed")
EXECUTOR_ERROR = RuntimeError("executor failed")


def make_command(number: int) -> Command:
    return Command(
        command_id=CommandId(f"runtime-command-{number}"),
        mission_id=MissionId("mission-1"),
        snapshot_id=SnapshotId("snapshot-1"),
        asset_id=AssetId("asset-1"),
        issued_at=FIXED_TIME,
        action="set_power",
        parameters={"power_kw": number},
    )


def make_event() -> Event:
    return Event(
        event_id=EventId("runtime-event-1"),
        event_type="decision_recorded",
        occurred_at=FIXED_TIME,
        recorded_at=FIXED_TIME,
        payload={},
    )


def make_context() -> EnergySystemContext:
    return EnergySystemContext(
        assets=(),
        states=(),
        power_flow=PowerFlow(
            pv_power_kw=0.0,
            load_power_kw=0.0,
            battery_power_kw=0.0,
            grid_power_kw=0.0,
        ),
    )


class RecordingPolicy(EMSPolicy):
    __slots__ = ("calls", "result")

    def __init__(self, result: DecisionResult) -> None:
        self.calls = 0
        self.result = result

    def evaluate(self, context: EnergySystemContext) -> DecisionResult:
        self.calls += 1
        return self.result


class RecordingDispatcher(CommandDispatcher):
    __slots__ = ("commands",)

    def __init__(self) -> None:
        self.commands: list[Command] = []

    def dispatch(self, command: Command) -> None:
        self.commands.append(command)


class RaisingDispatcher(CommandDispatcher):
    __slots__ = ("attempts", "fail_at")

    def __init__(self, fail_at: int = 0) -> None:
        self.attempts: list[Command] = []
        self.fail_at = fail_at

    def dispatch(self, command: Command) -> None:
        self.attempts.append(command)
        if len(self.attempts) - 1 == self.fail_at:
            raise DISPATCH_ERROR


def make_tick(
    result: DecisionResult,
    journal: EventJournal | None = None,
) -> JournaledEMSTick:
    source_journal = journal if journal is not None else EventJournal()
    return JournaledEMSTick(
        execution=JournaledEMSCycle(
            cycle=EMSCycle(context=make_context(), result=result),
            journal=source_journal,
        )
    )


def test_dispatch_delegates_once_with_exact_inputs_and_returns_source_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = DecisionResult(commands=(make_command(1),))
    tick = make_tick(result)
    dispatcher = RaisingDispatcher()
    calls: list[tuple[CommandDispatcher, DecisionResult]] = []

    def fake_execute(
        supplied_dispatcher: CommandDispatcher,
        supplied_result: DecisionResult,
    ) -> None:
        calls.append((supplied_dispatcher, supplied_result))

    monkeypatch.setattr(
        CommandExecutor,
        "execute",
        staticmethod(fake_execute),
    )

    dispatched = JournaledEMSRuntime.dispatch(tick, dispatcher)

    assert isinstance(dispatched, DispatchedJournaledEMSTick)
    assert calls == [(dispatcher, result)]
    assert dispatched.tick is tick
    assert dispatcher.attempts == []


def test_one_and_multiple_commands_follow_executor_order_and_identity() -> None:
    dispatcher = RecordingDispatcher()
    commands = (make_command(1), make_command(2), make_command(3))
    tick = make_tick(DecisionResult(commands=commands))

    dispatched = JournaledEMSRuntime.dispatch(tick, dispatcher)

    assert dispatched.tick is tick
    assert len(dispatcher.commands) == len(commands)
    assert all(
        actual is expected
        for actual, expected in zip(dispatcher.commands, commands, strict=True)
    )


def test_duplicate_command_references_remain_positional() -> None:
    dispatcher = RecordingDispatcher()
    command = make_command(1)
    tick = make_tick(DecisionResult(commands=(command, command)))

    JournaledEMSRuntime.dispatch(tick, dispatcher)

    assert len(dispatcher.commands) == 2
    assert dispatcher.commands[0] is command
    assert dispatcher.commands[1] is command


def test_empty_commands_still_delegate_once_and_return_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = DecisionResult.empty()
    tick = make_tick(result)
    dispatcher = RecordingDispatcher()
    calls = 0

    def fake_execute(
        supplied_dispatcher: CommandDispatcher,
        supplied_result: DecisionResult,
    ) -> None:
        nonlocal calls
        calls += 1
        assert supplied_dispatcher is dispatcher
        assert supplied_result is result

    monkeypatch.setattr(
        CommandExecutor,
        "execute",
        staticmethod(fake_execute),
    )

    dispatched = JournaledEMSRuntime.dispatch(tick, dispatcher)

    assert calls == 1
    assert dispatched.tick is tick


def test_events_are_not_processed_by_runtime_dispatch() -> None:
    dispatcher = RecordingDispatcher()
    result = DecisionResult(events=(make_event(),))
    tick = make_tick(result)

    JournaledEMSRuntime.dispatch(tick, dispatcher)

    assert dispatcher.commands == []
    assert tick.execution.cycle.result is result


def test_success_preserves_all_source_identities() -> None:
    result = DecisionResult(commands=(make_command(1),))
    journal = EventJournal()
    tick = make_tick(result, journal)
    execution = tick.execution
    cycle = execution.cycle

    dispatched = JournaledEMSRuntime.dispatch(tick, RecordingDispatcher())

    assert dispatched.tick is tick
    assert dispatched.tick.execution is execution
    assert dispatched.tick.execution.cycle is cycle
    assert dispatched.tick.execution.cycle.result is result
    assert dispatched.tick.execution.journal is journal


def test_dispatcher_failure_stops_later_commands_and_preserves_source() -> None:
    commands = (make_command(1), make_command(2), make_command(3))
    result = DecisionResult(commands=commands)
    journal = EventJournal()
    tick = make_tick(result, journal)
    dispatcher = RaisingDispatcher(fail_at=1)

    with pytest.raises(RuntimeError) as raised:
        JournaledEMSRuntime.dispatch(tick, dispatcher)

    assert raised.value is DISPATCH_ERROR
    assert len(dispatcher.attempts) == 2
    assert dispatcher.attempts[0] is commands[0]
    assert dispatcher.attempts[1] is commands[1]
    assert tick.execution.cycle.result is result
    assert tick.execution.journal is journal


def test_executor_exception_propagates_without_constructing_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tick = make_tick(DecisionResult.empty())

    def raise_from_executor(
        dispatcher: CommandDispatcher,
        decision_result: DecisionResult,
    ) -> None:
        raise EXECUTOR_ERROR

    def fail_if_constructed(
        source_tick: JournaledEMSTick,
    ) -> DispatchedJournaledEMSTick:
        raise AssertionError("dispatched result constructed after failure")

    monkeypatch.setattr(
        CommandExecutor,
        "execute",
        staticmethod(raise_from_executor),
    )
    monkeypatch.setattr(
        journaled_module,
        "DispatchedJournaledEMSTick",
        fail_if_constructed,
    )

    with pytest.raises(RuntimeError) as raised:
        JournaledEMSRuntime.dispatch(tick, RecordingDispatcher())

    assert raised.value is EXECUTOR_ERROR


def test_dispatch_does_not_reevaluate_policy_or_call_runtime_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = RecordingPolicy(DecisionResult(commands=(make_command(1),)))
    tick = JournaledEMSRuntime.tick(policy, make_context(), EventJournal())

    def fail_if_tick_called(
        supplied_policy: EMSPolicy,
        context: EnergySystemContext,
        journal: EventJournal,
    ) -> JournaledEMSTick:
        raise AssertionError("dispatch called runtime tick")

    monkeypatch.setattr(
        JournaledEMSRuntime,
        "tick",
        staticmethod(fail_if_tick_called),
    )

    JournaledEMSRuntime.dispatch(tick, RecordingDispatcher())

    assert policy.calls == 1


@pytest.mark.parametrize(
    ("tick", "dispatcher", "field_name"),
    [
        (
            cast(JournaledEMSTick, object()),
            RecordingDispatcher(),
            "tick",
        ),
        (
            make_tick(DecisionResult.empty()),
            cast(CommandDispatcher, object()),
            "dispatcher",
        ),
    ],
)
def test_invalid_inputs_fail_before_executor_delegation(
    monkeypatch: pytest.MonkeyPatch,
    tick: JournaledEMSTick,
    dispatcher: CommandDispatcher,
    field_name: str,
) -> None:
    def fail_if_called(
        supplied_dispatcher: CommandDispatcher,
        decision_result: DecisionResult,
    ) -> None:
        raise AssertionError("invalid input reached executor")

    monkeypatch.setattr(
        CommandExecutor,
        "execute",
        staticmethod(fail_if_called),
    )

    with pytest.raises(TypeError, match=field_name):
        JournaledEMSRuntime.dispatch(tick, dispatcher)


def test_dispatched_tick_is_frozen_slotted_and_has_exact_field() -> None:
    tick = make_tick(DecisionResult.empty())
    dispatched = DispatchedJournaledEMSTick(tick=tick)

    assert tuple(field.name for field in fields(DispatchedJournaledEMSTick)) == (
        "tick",
    )
    assert DispatchedJournaledEMSTick.__slots__ == ("tick",)
    assert not hasattr(dispatched, "__dict__")
    assert dispatched.tick is tick
    with pytest.raises(FrozenInstanceError):
        cast(Any, dispatched).tick = tick


def test_invalid_direct_construction_raises_type_error() -> None:
    with pytest.raises(TypeError, match="tick"):
        DispatchedJournaledEMSTick(
            tick=cast(JournaledEMSTick, object()),
        )


def test_dispatch_signature_contains_only_explicit_dependencies() -> None:
    assert list(signature(JournaledEMSRuntime.dispatch).parameters) == [
        "tick",
        "dispatcher",
    ]
