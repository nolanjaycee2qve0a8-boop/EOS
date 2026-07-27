"""Tests for dispatch-progression runtime lifecycle integration."""

from datetime import UTC, datetime
from inspect import signature
from typing import Any, cast

import pytest

from kernel.context import EnergySystemContext
from kernel.cycle import EMSCycle, JournaledEMSCycle
from kernel.decision import DecisionResult
from kernel.dispatch import CommandDispatcher
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
    DispatchProgressionRuntime,
    JournaledEMSRuntime,
    JournaledEMSTick,
)

FIXED_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
POLICY_ERROR = RuntimeError("decision failed")
DISPATCH_ERROR = RuntimeError("dispatch failed")


def make_context(power_kw: float = 0.0) -> EnergySystemContext:
    return EnergySystemContext(
        assets=(),
        states=(),
        power_flow=PowerFlow(
            pv_power_kw=power_kw,
            load_power_kw=power_kw,
            battery_power_kw=0.0,
            grid_power_kw=0.0,
        ),
    )


def make_command() -> Command:
    return Command(
        command_id=CommandId("integration-command-1"),
        mission_id=MissionId("mission-1"),
        snapshot_id=SnapshotId("snapshot-1"),
        asset_id=AssetId("asset-1"),
        issued_at=FIXED_TIME,
        action="set_power",
        parameters={"power_kw": 1},
    )


def make_event(number: int) -> Event:
    return Event(
        event_id=EventId(f"integration-event-{number}"),
        event_type="decision_recorded",
        occurred_at=FIXED_TIME,
        recorded_at=FIXED_TIME,
        payload={"number": number},
    )


class RecordingPolicy(EMSPolicy):
    __slots__ = ("calls", "contexts", "result")

    def __init__(self, result: DecisionResult) -> None:
        self.calls = 0
        self.contexts: list[EnergySystemContext] = []
        self.result = result

    def evaluate(self, context: EnergySystemContext) -> DecisionResult:
        self.calls += 1
        self.contexts.append(context)
        return self.result


class RaisingPolicy(EMSPolicy):
    __slots__ = ()

    def evaluate(self, context: EnergySystemContext) -> DecisionResult:
        raise POLICY_ERROR


class RecordingDispatcher(CommandDispatcher):
    __slots__ = ("commands",)

    def __init__(self) -> None:
        self.commands: list[Command] = []

    def dispatch(self, command: Command) -> None:
        self.commands.append(command)


class RaisingDispatcher(CommandDispatcher):
    __slots__ = ("commands",)

    def __init__(self) -> None:
        self.commands: list[Command] = []

    def dispatch(self, command: Command) -> None:
        self.commands.append(command)
        raise DISPATCH_ERROR


def make_tick(
    context: EnergySystemContext,
    result: DecisionResult,
    journal: EventJournal,
) -> JournaledEMSTick:
    return JournaledEMSTick(
        execution=JournaledEMSCycle(
            cycle=EMSCycle(context=context, result=result),
            journal=journal,
        )
    )


def test_lifecycle_order_once_and_exact_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = RecordingPolicy(DecisionResult.empty())
    context = make_context()
    journal = EventJournal()
    dispatcher = RecordingDispatcher()
    next_policy = RecordingPolicy(DecisionResult.empty())
    next_context = make_context(1.0)
    tick = make_tick(context, policy.result, journal)
    dispatched = DispatchedJournaledEMSTick(tick=tick)
    expected = make_tick(next_context, next_policy.result, journal)
    order: list[str] = []

    def fake_tick(
        supplied_policy: EMSPolicy,
        supplied_context: EnergySystemContext,
        supplied_journal: EventJournal,
    ) -> JournaledEMSTick:
        order.append("tick")
        assert supplied_policy is policy
        assert supplied_context is context
        assert supplied_journal is journal
        return tick

    def fake_dispatch(
        supplied_tick: JournaledEMSTick,
        supplied_dispatcher: CommandDispatcher,
    ) -> DispatchedJournaledEMSTick:
        order.append("dispatch")
        assert supplied_tick is tick
        assert supplied_dispatcher is dispatcher
        return dispatched

    def fake_progress(
        supplied_dispatch: DispatchedJournaledEMSTick,
        supplied_policy: EMSPolicy,
        supplied_context: EnergySystemContext,
    ) -> JournaledEMSTick:
        order.append("progress")
        assert supplied_dispatch is dispatched
        assert supplied_policy is next_policy
        assert supplied_context is next_context
        return expected

    monkeypatch.setattr(JournaledEMSRuntime, "tick", staticmethod(fake_tick))
    monkeypatch.setattr(
        JournaledEMSRuntime,
        "dispatch",
        staticmethod(fake_dispatch),
    )
    monkeypatch.setattr(
        JournaledEMSRuntime,
        "progress_after_dispatch",
        staticmethod(fake_progress),
    )

    actual = DispatchProgressionRuntime.execute(
        policy,
        context,
        journal,
        dispatcher,
        next_policy,
        next_context,
    )

    assert order == ["tick", "dispatch", "progress"]
    assert actual is expected
    assert policy.calls == 0
    assert next_policy.calls == 0


def test_complete_lifecycle_preserves_domain_identities() -> None:
    command = make_command()
    first_event = make_event(1)
    next_event = make_event(2)
    first_result = DecisionResult(
        commands=(command,),
        events=(first_event,),
    )
    next_result = DecisionResult(events=(next_event,))
    policy = RecordingPolicy(first_result)
    next_policy = RecordingPolicy(next_result)
    context = make_context()
    next_context = make_context(2.0)
    journal = EventJournal()
    dispatcher = RecordingDispatcher()

    progressed = DispatchProgressionRuntime.execute(
        policy,
        context,
        journal,
        dispatcher,
        next_policy,
        next_context,
    )

    records = progressed.execution.journal.events()
    assert dispatcher.commands == [command]
    assert dispatcher.commands[0] is command
    assert policy.calls == 1
    assert policy.contexts == [context]
    assert next_policy.calls == 1
    assert next_policy.contexts == [next_context]
    assert progressed.execution.cycle.context is next_context
    assert progressed.execution.cycle.result is next_result
    assert tuple(record.sequence for record in records) == (0, 1)
    assert records[0].event is first_event
    assert records[1].event is next_event
    assert journal.events() == ()


def test_dispatch_failure_prevents_progression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command = make_command()
    result = DecisionResult(commands=(command,))
    context = make_context()
    source_tick = make_tick(context, result, EventJournal())
    dispatcher = RaisingDispatcher()
    next_policy = RecordingPolicy(DecisionResult.empty())
    progress_calls = 0

    def fake_tick(
        policy: EMSPolicy,
        supplied_context: EnergySystemContext,
        journal: EventJournal,
    ) -> JournaledEMSTick:
        return source_tick

    def fail_if_progressed(
        dispatched: DispatchedJournaledEMSTick,
        policy: EMSPolicy,
        supplied_context: EnergySystemContext,
    ) -> JournaledEMSTick:
        nonlocal progress_calls
        progress_calls += 1
        raise AssertionError("dispatch failure reached progression")

    monkeypatch.setattr(JournaledEMSRuntime, "tick", staticmethod(fake_tick))
    monkeypatch.setattr(
        JournaledEMSRuntime,
        "progress_after_dispatch",
        staticmethod(fail_if_progressed),
    )

    with pytest.raises(RuntimeError) as raised:
        DispatchProgressionRuntime.execute(
            RecordingPolicy(result),
            context,
            EventJournal(),
            dispatcher,
            next_policy,
            make_context(),
        )

    assert raised.value is DISPATCH_ERROR
    assert dispatcher.commands == [command]
    assert progress_calls == 0
    assert next_policy.calls == 0
    assert source_tick.execution.cycle.result is result


def test_decision_failure_prevents_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatch_calls = 0

    def fail_if_dispatched(
        tick: JournaledEMSTick,
        dispatcher: CommandDispatcher,
    ) -> DispatchedJournaledEMSTick:
        nonlocal dispatch_calls
        dispatch_calls += 1
        raise AssertionError("decision failure reached dispatch")

    monkeypatch.setattr(
        JournaledEMSRuntime,
        "dispatch",
        staticmethod(fail_if_dispatched),
    )

    with pytest.raises(RuntimeError) as raised:
        DispatchProgressionRuntime.execute(
            RaisingPolicy(),
            make_context(),
            EventJournal(),
            RecordingDispatcher(),
            RecordingPolicy(DecisionResult.empty()),
            make_context(),
        )

    assert raised.value is POLICY_ERROR
    assert dispatch_calls == 0


@pytest.mark.parametrize(
    (
        "policy",
        "context",
        "journal",
        "dispatcher",
        "next_policy",
        "next_context",
        "field_name",
    ),
    [
        (
            cast(EMSPolicy, object()),
            make_context(),
            EventJournal(),
            RecordingDispatcher(),
            RecordingPolicy(DecisionResult.empty()),
            make_context(),
            "policy",
        ),
        (
            RecordingPolicy(DecisionResult.empty()),
            cast(EnergySystemContext, object()),
            EventJournal(),
            RecordingDispatcher(),
            RecordingPolicy(DecisionResult.empty()),
            make_context(),
            "context",
        ),
        (
            RecordingPolicy(DecisionResult.empty()),
            make_context(),
            cast(EventJournal, object()),
            RecordingDispatcher(),
            RecordingPolicy(DecisionResult.empty()),
            make_context(),
            "journal",
        ),
        (
            RecordingPolicy(DecisionResult.empty()),
            make_context(),
            EventJournal(),
            cast(CommandDispatcher, object()),
            RecordingPolicy(DecisionResult.empty()),
            make_context(),
            "dispatcher",
        ),
        (
            RecordingPolicy(DecisionResult.empty()),
            make_context(),
            EventJournal(),
            RecordingDispatcher(),
            cast(EMSPolicy, object()),
            make_context(),
            "next_policy",
        ),
        (
            RecordingPolicy(DecisionResult.empty()),
            make_context(),
            EventJournal(),
            RecordingDispatcher(),
            RecordingPolicy(DecisionResult.empty()),
            cast(EnergySystemContext, object()),
            "next_context",
        ),
    ],
)
def test_invalid_inputs_fail_before_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    policy: EMSPolicy,
    context: EnergySystemContext,
    journal: EventJournal,
    dispatcher: CommandDispatcher,
    next_policy: EMSPolicy,
    next_context: EnergySystemContext,
    field_name: str,
) -> None:
    def fail_if_called(
        supplied_policy: EMSPolicy,
        supplied_context: EnergySystemContext,
        supplied_journal: EventJournal,
    ) -> JournaledEMSTick:
        raise AssertionError("invalid input reached lifecycle")

    monkeypatch.setattr(
        JournaledEMSRuntime,
        "tick",
        staticmethod(fail_if_called),
    )

    with pytest.raises(TypeError, match=field_name):
        DispatchProgressionRuntime.execute(
            policy,
            context,
            journal,
            dispatcher,
            next_policy,
            next_context,
        )


def test_integration_is_stateless_with_explicit_signature() -> None:
    integration = DispatchProgressionRuntime()

    assert DispatchProgressionRuntime.__slots__ == ()
    assert not hasattr(integration, "__dict__")
    assert list(signature(DispatchProgressionRuntime.execute).parameters) == [
        "policy",
        "context",
        "journal",
        "dispatcher",
        "next_policy",
        "next_context",
    ]
    with pytest.raises(AttributeError):
        cast(Any, integration).policy = RecordingPolicy(DecisionResult.empty())
