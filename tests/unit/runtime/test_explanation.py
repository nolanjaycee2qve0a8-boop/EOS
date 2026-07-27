"""Tests for the immutable decision explanation observation boundary."""

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
    DecisionExplanation,
    DispatchedJournaledEMSTick,
    ExecutionAudit,
    JournaledEMSRuntime,
    JournaledEMSTick,
    RuntimeExecutionTrace,
    RuntimeReplay,
)

FIXED_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


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


def make_command(number: int = 1) -> Command:
    return Command(
        command_id=CommandId(f"explanation-command-{number}"),
        mission_id=MissionId("mission-1"),
        snapshot_id=SnapshotId("snapshot-1"),
        asset_id=AssetId("asset-1"),
        issued_at=FIXED_TIME,
        action="set_power",
        parameters={"power_kw": number},
    )


def make_event(number: int) -> Event:
    return Event(
        event_id=EventId(f"explanation-event-{number}"),
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


def make_audit(
    number: int = 1,
) -> tuple[
    ExecutionAudit,
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
        make_context(float(number)),
    )
    trace = RuntimeExecutionTrace.create(source, dispatched, progressed)
    return (
        ExecutionAudit.create(trace),
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


def fabricate_audit(
    trace: RuntimeExecutionTrace,
    source: JournaledEMSTick,
    dispatched: DispatchedJournaledEMSTick,
    progressed: JournaledEMSTick,
) -> ExecutionAudit:
    audit = object.__new__(ExecutionAudit)
    object.__setattr__(audit, "trace", trace)
    object.__setattr__(audit, "source_tick", source)
    object.__setattr__(audit, "dispatched_tick", dispatched)
    object.__setattr__(audit, "progressed_tick", progressed)
    return audit


def test_explanation_preserves_exact_decision_artifact_identities() -> None:
    audit, _, _, _ = make_audit()
    source_cycle = audit.source_tick.execution.cycle
    source_record = audit.source_tick.execution.journal.events()[0]

    explanation = DecisionExplanation.create(audit)

    assert explanation.audit is audit
    assert explanation.trace is audit.trace
    assert explanation.source_context is source_cycle.context
    assert explanation.decision_result is source_cycle.result
    assert explanation.decision_result.commands[0] is source_cycle.result.commands[0]
    assert explanation.decision_result.events[0] is source_cycle.result.events[0]
    assert audit.progressed_tick.execution.journal.events()[0] is source_record


def test_repeated_explanations_share_no_explanation_state() -> None:
    audit, _, _, _ = make_audit()

    first = DecisionExplanation.create(audit)
    second = DecisionExplanation.create(audit)

    assert first is not second
    assert first.audit is second.audit is audit
    assert first.trace is second.trace is audit.trace
    assert first.source_context is second.source_context
    assert first.decision_result is second.decision_result


def test_explanation_invokes_no_execution_audit_or_replay_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit, source_policy, next_policy, dispatcher = make_audit()
    source_calls = source_policy.calls
    next_calls = next_policy.calls
    dispatched_commands = tuple(dispatcher.commands)

    def fail_if_called(*args: object) -> None:
        raise AssertionError("explanation invoked an execution boundary")

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
    monkeypatch.setattr(
        ExecutionAudit,
        "create",
        classmethod(fail_if_called),
    )
    monkeypatch.setattr(FixedPolicy, "evaluate", fail_if_called)
    monkeypatch.setattr(RecordingDispatcher, "dispatch", fail_if_called)

    explanation = DecisionExplanation.create(audit)

    assert explanation.audit is audit
    assert source_policy.calls == source_calls
    assert next_policy.calls == next_calls
    assert tuple(dispatcher.commands) == dispatched_commands


def test_explanation_does_not_mutate_or_append_journals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit, _, _, _ = make_audit()
    source_journal = audit.source_tick.execution.journal
    progressed_journal = audit.progressed_tick.execution.journal
    source_records = source_journal.events()
    progressed_records = progressed_journal.events()

    def fail_if_appended(
        journal: EventJournal,
        record: object,
    ) -> EventJournal:
        raise AssertionError("explanation appended an EventRecord")

    monkeypatch.setattr(EventJournal, "append", fail_if_appended)

    explanation = DecisionExplanation.create(audit)

    assert explanation.audit.source_tick.execution.journal is source_journal
    assert explanation.audit.progressed_tick.execution.journal is progressed_journal
    assert source_journal.events() is source_records
    assert progressed_journal.events() is progressed_records


@pytest.mark.parametrize("invalid_audit", [None, object()])
def test_invalid_audit_type_is_rejected(invalid_audit: object) -> None:
    with pytest.raises(TypeError, match="audit"):
        DecisionExplanation.create(cast(ExecutionAudit, invalid_audit))


def test_broken_audit_trace_identity_is_rejected() -> None:
    first, _, _, _ = make_audit(1)
    second, _, _, _ = make_audit(10)
    broken = fabricate_audit(
        first.trace,
        second.source_tick,
        first.dispatched_tick,
        first.progressed_tick,
    )

    with pytest.raises(ValueError, match="exact trace source_tick"):
        DecisionExplanation.create(broken)


def test_broken_audit_progression_identity_is_rejected() -> None:
    audit, _, _, _ = make_audit()
    broken = fabricate_audit(
        audit.trace,
        audit.source_tick,
        audit.dispatched_tick,
        make_empty_tick(EventJournal()),
    )

    with pytest.raises(ValueError, match="exact trace progressed_tick"):
        DecisionExplanation.create(broken)


def test_direct_construction_rejects_reconstructed_decision_result() -> None:
    audit, _, _, _ = make_audit()
    source_cycle = audit.source_tick.execution.cycle
    reconstructed = DecisionResult(
        commands=source_cycle.result.commands,
        events=source_cycle.result.events,
    )

    with pytest.raises(ValueError, match="exact source decision result"):
        DecisionExplanation(
            audit=audit,
            trace=audit.trace,
            source_context=source_cycle.context,
            decision_result=reconstructed,
        )


def test_explanation_is_frozen_slotted_and_has_exact_fields() -> None:
    explanation = DecisionExplanation.create(make_audit()[0])

    assert tuple(field.name for field in fields(DecisionExplanation)) == (
        "audit",
        "trace",
        "source_context",
        "decision_result",
    )
    assert DecisionExplanation.__slots__ == (
        "audit",
        "trace",
        "source_context",
        "decision_result",
    )
    assert not hasattr(explanation, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, explanation).audit = explanation.audit


def test_create_accepts_only_audit() -> None:
    assert list(signature(DecisionExplanation.create).parameters) == ["audit"]
