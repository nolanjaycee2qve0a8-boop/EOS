"""Tests for the immutable execution audit observation boundary."""

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from inspect import signature
from typing import Any, cast

import pytest

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
    ExecutionAudit,
    JournaledEMSRuntime,
    JournaledEMSTick,
    RuntimeExecutionTrace,
    RuntimeReplay,
)

FIXED_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


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


def make_command(number: int = 1) -> Command:
    return Command(
        command_id=CommandId(f"audit-command-{number}"),
        mission_id=MissionId("mission-1"),
        snapshot_id=SnapshotId("snapshot-1"),
        asset_id=AssetId("asset-1"),
        issued_at=FIXED_TIME,
        action="set_power",
        parameters={"power_kw": number},
    )


def make_event(number: int) -> Event:
    return Event(
        event_id=EventId(f"audit-event-{number}"),
        event_type="decision_recorded",
        occurred_at=FIXED_TIME,
        recorded_at=FIXED_TIME,
        payload={"number": number},
    )


class FixedPolicy(EMSPolicy):
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


def make_trace(
    number: int = 1,
) -> tuple[
    RuntimeExecutionTrace,
    FixedPolicy,
    FixedPolicy,
    RecordingDispatcher,
]:
    source_policy = FixedPolicy(
        DecisionResult(
            commands=(make_command(number),),
            events=(make_event(number),),
        )
    )
    next_policy = FixedPolicy(DecisionResult(events=(make_event(number + 1),)))
    dispatcher = RecordingDispatcher()
    source = JournaledEMSRuntime.tick(
        source_policy,
        make_context(),
        EventJournal(),
    )
    dispatched = JournaledEMSRuntime.dispatch(source, dispatcher)
    progressed = JournaledEMSRuntime.progress_after_dispatch(
        dispatched,
        next_policy,
        make_context(),
    )
    return (
        RuntimeExecutionTrace.create(source, dispatched, progressed),
        source_policy,
        next_policy,
        dispatcher,
    )


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


def fabricate_trace(
    source: JournaledEMSTick,
    dispatched: DispatchedJournaledEMSTick,
    progressed: JournaledEMSTick,
) -> RuntimeExecutionTrace:
    trace = object.__new__(RuntimeExecutionTrace)
    object.__setattr__(trace, "source_tick", source)
    object.__setattr__(trace, "dispatched_tick", dispatched)
    object.__setattr__(trace, "progressed_tick", progressed)
    return trace


def test_audit_preserves_trace_and_lifecycle_identities() -> None:
    trace, _, _, _ = make_trace()
    source_record = trace.source_tick.execution.journal.events()[0]

    audit = ExecutionAudit.create(trace)

    assert audit.trace is trace
    assert audit.source_tick is trace.source_tick
    assert audit.dispatched_tick is trace.dispatched_tick
    assert audit.progressed_tick is trace.progressed_tick
    assert audit.dispatched_tick.tick is audit.source_tick
    assert audit.progressed_tick.execution.journal.events()[0] is source_record


def test_repeated_audits_share_no_audit_state() -> None:
    trace, _, _, _ = make_trace()

    first = ExecutionAudit.create(trace)
    second = ExecutionAudit.create(trace)

    assert first is not second
    assert first.trace is second.trace is trace
    assert first.source_tick is second.source_tick is trace.source_tick
    assert first.dispatched_tick is second.dispatched_tick
    assert first.progressed_tick is second.progressed_tick


def test_audit_creation_invokes_no_execution_or_replay_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace, source_policy, next_policy, dispatcher = make_trace()
    source_calls = source_policy.calls
    next_calls = next_policy.calls
    dispatched_commands = tuple(dispatcher.commands)

    def fail_if_called(*args: object) -> None:
        raise AssertionError("audit invoked an execution boundary")

    monkeypatch.setattr(
        JournaledEMSRuntime,
        "tick",
        staticmethod(fail_if_called),
    )
    monkeypatch.setattr(
        JournaledEMSRuntime,
        "progress",
        staticmethod(fail_if_called),
    )
    monkeypatch.setattr(
        JournaledEMSRuntime,
        "dispatch",
        staticmethod(fail_if_called),
    )
    monkeypatch.setattr(
        JournaledEMSRuntime,
        "progress_after_dispatch",
        staticmethod(fail_if_called),
    )
    monkeypatch.setattr(
        CommandExecutor,
        "execute",
        staticmethod(fail_if_called),
    )
    monkeypatch.setattr(
        RuntimeReplay,
        "replay",
        staticmethod(fail_if_called),
    )
    monkeypatch.setattr(FixedPolicy, "evaluate", fail_if_called)
    monkeypatch.setattr(RecordingDispatcher, "dispatch", fail_if_called)

    audit = ExecutionAudit.create(trace)

    assert audit.trace is trace
    assert source_policy.calls == source_calls
    assert next_policy.calls == next_calls
    assert tuple(dispatcher.commands) == dispatched_commands


def test_audit_does_not_mutate_or_append_journals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace, _, _, _ = make_trace()
    source_journal = trace.source_tick.execution.journal
    progressed_journal = trace.progressed_tick.execution.journal
    source_records = source_journal.events()
    progressed_records = progressed_journal.events()

    def fail_if_appended(
        journal: EventJournal,
        record: object,
    ) -> EventJournal:
        raise AssertionError("audit appended an EventRecord")

    monkeypatch.setattr(EventJournal, "append", fail_if_appended)

    audit = ExecutionAudit.create(trace)

    assert audit.source_tick.execution.journal is source_journal
    assert audit.progressed_tick.execution.journal is progressed_journal
    assert source_journal.events() is source_records
    assert progressed_journal.events() is progressed_records


@pytest.mark.parametrize("invalid_trace", [None, object()])
def test_invalid_trace_type_is_rejected(invalid_trace: object) -> None:
    with pytest.raises(TypeError, match="trace"):
        ExecutionAudit.create(cast(RuntimeExecutionTrace, invalid_trace))


def test_broken_dispatch_identity_chain_is_rejected() -> None:
    first, _, _, _ = make_trace(1)
    second, _, _, _ = make_trace(10)
    broken = fabricate_trace(
        first.source_tick,
        second.dispatched_tick,
        first.progressed_tick,
    )

    with pytest.raises(ValueError, match="exact source_tick"):
        ExecutionAudit.create(broken)


def test_broken_progression_journal_identity_chain_is_rejected() -> None:
    trace, _, _, _ = make_trace()
    broken = fabricate_trace(
        trace.source_tick,
        trace.dispatched_tick,
        make_empty_tick(EventJournal()),
    )

    with pytest.raises(ValueError, match="EventRecord identities"):
        ExecutionAudit.create(broken)


def test_direct_construction_rejects_non_trace_lifecycle_identity() -> None:
    first, _, _, _ = make_trace(1)
    second, _, _, _ = make_trace(10)

    with pytest.raises(ValueError, match="exact trace source_tick"):
        ExecutionAudit(
            trace=first,
            source_tick=second.source_tick,
            dispatched_tick=first.dispatched_tick,
            progressed_tick=first.progressed_tick,
        )


def test_execution_audit_is_frozen_slotted_and_has_exact_fields() -> None:
    audit = ExecutionAudit.create(make_trace()[0])

    assert tuple(field.name for field in fields(ExecutionAudit)) == (
        "trace",
        "source_tick",
        "dispatched_tick",
        "progressed_tick",
    )
    assert ExecutionAudit.__slots__ == (
        "trace",
        "source_tick",
        "dispatched_tick",
        "progressed_tick",
    )
    assert not hasattr(audit, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, audit).trace = audit.trace


def test_create_is_the_only_audit_entry_point_argument() -> None:
    assert list(signature(ExecutionAudit.create).parameters) == ["trace"]
