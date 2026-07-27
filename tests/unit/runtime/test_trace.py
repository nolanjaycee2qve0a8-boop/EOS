"""Tests for the immutable runtime execution trace boundary."""

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
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
    JournaledEMSRuntime,
    JournaledEMSTick,
    RuntimeExecutionTrace,
)

FIXED_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
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


def make_command(number: int) -> Command:
    return Command(
        command_id=CommandId(f"trace-command-{number}"),
        mission_id=MissionId("mission-1"),
        snapshot_id=SnapshotId("snapshot-1"),
        asset_id=AssetId("asset-1"),
        issued_at=FIXED_TIME,
        action="set_power",
        parameters={"power_kw": number},
    )


def make_event(number: int) -> Event:
    return Event(
        event_id=EventId(f"trace-event-{number}"),
        event_type="decision_recorded",
        occurred_at=FIXED_TIME,
        recorded_at=FIXED_TIME,
        payload={"number": number},
    )


class FixedPolicy(EMSPolicy):
    __slots__ = ("result",)

    def __init__(self, result: DecisionResult) -> None:
        self.result = result

    def evaluate(self, context: EnergySystemContext) -> DecisionResult:
        return self.result


class RecordingDispatcher(CommandDispatcher):
    __slots__ = ("commands",)

    def __init__(self) -> None:
        self.commands: list[Command] = []

    def dispatch(self, command: Command) -> None:
        self.commands.append(command)


class RaisingDispatcher(CommandDispatcher):
    __slots__ = ()

    def dispatch(self, command: Command) -> None:
        raise DISPATCH_ERROR


def complete_lifecycle(
    number: int = 1,
) -> tuple[
    JournaledEMSTick,
    DispatchedJournaledEMSTick,
    JournaledEMSTick,
]:
    source = JournaledEMSRuntime.tick(
        FixedPolicy(
            DecisionResult(
                commands=(make_command(number),),
                events=(make_event(number),),
            )
        ),
        make_context(),
        EventJournal(),
    )
    dispatched = JournaledEMSRuntime.dispatch(
        source,
        RecordingDispatcher(),
    )
    progressed = JournaledEMSRuntime.progress_after_dispatch(
        dispatched,
        FixedPolicy(DecisionResult(events=(make_event(number + 1),))),
        make_context(float(number)),
    )
    return source, dispatched, progressed


def make_empty_tick(journal: EventJournal) -> JournaledEMSTick:
    return JournaledEMSTick(
        execution=JournaledEMSCycle(
            cycle=EMSCycle(
                context=make_context(),
                result=DecisionResult.empty(),
            ),
            journal=journal,
        )
    )


def test_trace_preserves_complete_lifecycle_identities() -> None:
    source, dispatched, progressed = complete_lifecycle()
    source_result = source.execution.cycle.result
    source_journal = source.execution.journal
    source_record = source_journal.events()[0]
    progressed_result = progressed.execution.cycle.result

    trace = RuntimeExecutionTrace.create(
        source,
        dispatched,
        progressed,
    )

    assert trace.source_tick is source
    assert trace.dispatched_tick is dispatched
    assert trace.progressed_tick is progressed
    assert trace.dispatched_tick.tick is trace.source_tick
    assert trace.source_tick.execution.cycle.result is source_result
    assert trace.source_tick.execution.journal is source_journal
    assert trace.progressed_tick.execution.cycle.result is progressed_result
    assert trace.progressed_tick.execution.journal.events()[0] is source_record
    assert (
        trace.source_tick.execution.cycle.result.commands[0]
        is source_result.commands[0]
    )


def test_trace_creation_does_not_recalculate_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, dispatched, progressed = complete_lifecycle()

    def fail_if_runtime_called(*args: object) -> None:
        raise AssertionError("trace construction invoked runtime")

    monkeypatch.setattr(
        JournaledEMSRuntime,
        "tick",
        staticmethod(fail_if_runtime_called),
    )
    monkeypatch.setattr(
        JournaledEMSRuntime,
        "dispatch",
        staticmethod(fail_if_runtime_called),
    )
    monkeypatch.setattr(
        JournaledEMSRuntime,
        "progress_after_dispatch",
        staticmethod(fail_if_runtime_called),
    )

    trace = RuntimeExecutionTrace.create(source, dispatched, progressed)

    assert trace.source_tick is source
    assert trace.progressed_tick is progressed


def test_empty_event_progression_preserves_exact_journal_identity() -> None:
    source = JournaledEMSRuntime.tick(
        FixedPolicy(DecisionResult(events=(make_event(1),))),
        make_context(),
        EventJournal(),
    )
    dispatched = JournaledEMSRuntime.dispatch(
        source,
        RecordingDispatcher(),
    )
    progressed = JournaledEMSRuntime.progress_after_dispatch(
        dispatched,
        FixedPolicy(DecisionResult.empty()),
        make_context(),
    )

    trace = RuntimeExecutionTrace.create(source, dispatched, progressed)

    assert trace.progressed_tick.execution.journal is source.execution.journal


def test_different_lifecycles_do_not_share_trace_state() -> None:
    first = complete_lifecycle(1)
    second = complete_lifecycle(10)

    first_trace = RuntimeExecutionTrace.create(*first)
    second_trace = RuntimeExecutionTrace.create(*second)

    assert first_trace is not second_trace
    assert first_trace.source_tick is not second_trace.source_tick
    assert first_trace.dispatched_tick is not second_trace.dispatched_tick
    assert first_trace.progressed_tick is not second_trace.progressed_tick
    assert not hasattr(first_trace, "__dict__")
    assert not hasattr(second_trace, "__dict__")


def test_failed_dispatch_cannot_produce_partial_trace() -> None:
    source = JournaledEMSRuntime.tick(
        FixedPolicy(DecisionResult(commands=(make_command(1),))),
        make_context(),
        EventJournal(),
    )

    with pytest.raises(RuntimeError) as raised:
        JournaledEMSRuntime.dispatch(source, RaisingDispatcher())

    assert raised.value is DISPATCH_ERROR
    with pytest.raises(TypeError, match="dispatched_tick"):
        RuntimeExecutionTrace.create(
            source,
            cast(DispatchedJournaledEMSTick, object()),
            make_empty_tick(source.execution.journal),
        )


def test_mismatched_dispatch_relationship_is_rejected() -> None:
    source, _, progressed = complete_lifecycle(1)
    other_source, other_dispatched, _ = complete_lifecycle(10)

    with pytest.raises(ValueError, match="exact source_tick"):
        RuntimeExecutionTrace.create(
            source,
            other_dispatched,
            progressed,
        )

    assert other_dispatched.tick is other_source


def test_mismatched_journal_progression_is_rejected() -> None:
    source, dispatched, _ = complete_lifecycle()
    unrelated_progressed = make_empty_tick(EventJournal())

    with pytest.raises(ValueError, match="EventRecord identities"):
        RuntimeExecutionTrace.create(
            source,
            dispatched,
            unrelated_progressed,
        )


@pytest.mark.parametrize(
    ("source", "dispatched", "progressed", "field_name"),
    [
        (
            cast(JournaledEMSTick, object()),
            complete_lifecycle()[1],
            complete_lifecycle()[2],
            "source_tick",
        ),
        (
            complete_lifecycle()[0],
            cast(DispatchedJournaledEMSTick, object()),
            complete_lifecycle()[2],
            "dispatched_tick",
        ),
        (
            complete_lifecycle()[0],
            complete_lifecycle()[1],
            cast(JournaledEMSTick, object()),
            "progressed_tick",
        ),
    ],
)
def test_invalid_types_are_rejected(
    source: JournaledEMSTick,
    dispatched: DispatchedJournaledEMSTick,
    progressed: JournaledEMSTick,
    field_name: str,
) -> None:
    with pytest.raises(TypeError, match=field_name):
        RuntimeExecutionTrace.create(source, dispatched, progressed)


def test_trace_is_frozen_slotted_and_contains_exact_fields() -> None:
    trace = RuntimeExecutionTrace.create(*complete_lifecycle())

    assert tuple(field.name for field in fields(RuntimeExecutionTrace)) == (
        "source_tick",
        "dispatched_tick",
        "progressed_tick",
    )
    assert RuntimeExecutionTrace.__slots__ == (
        "source_tick",
        "dispatched_tick",
        "progressed_tick",
    )
    with pytest.raises(FrozenInstanceError):
        cast(Any, trace).source_tick = trace.source_tick
