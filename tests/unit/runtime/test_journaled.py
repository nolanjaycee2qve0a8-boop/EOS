"""Tests for the stateless journaled EMS runtime tick boundary."""

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from inspect import signature
from typing import Any, cast

import pytest

from kernel.context import EnergySystemContext
from kernel.cycle import EMSCycle, JournaledEMSCycle
from kernel.decision import DecisionResult
from kernel.domain import Event
from kernel.event import EventJournal
from kernel.execution import JournaledEMSExecutionService
from kernel.ids import EventId
from kernel.policy import EMSPolicy
from kernel.power import PowerFlow
from kernel.runtime import JournaledEMSRuntime, JournaledEMSTick

FIXED_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
EMPTY_RESULT = DecisionResult.empty()
POLICY_ERROR = RuntimeError("policy failed")
SERVICE_ERROR = RuntimeError("service failed")


def make_event(number: int) -> Event:
    return Event(
        event_id=EventId(f"event-{number}"),
        event_type="decision_recorded",
        occurred_at=FIXED_TIME,
        recorded_at=FIXED_TIME,
        payload={"number": number},
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
    __slots__ = ("calls", "received_context", "result")

    def __init__(self, result: DecisionResult) -> None:
        self.calls = 0
        self.received_context: EnergySystemContext | None = None
        self.result = result

    def evaluate(self, context: EnergySystemContext) -> DecisionResult:
        self.calls += 1
        self.received_context = context
        return self.result


class RaisingPolicy(EMSPolicy):
    __slots__ = ()

    def evaluate(self, context: EnergySystemContext) -> DecisionResult:
        raise POLICY_ERROR


def make_execution(
    context: EnergySystemContext,
    result: DecisionResult,
    journal: EventJournal,
) -> JournaledEMSCycle:
    return JournaledEMSCycle(
        cycle=EMSCycle(context=context, result=result),
        journal=journal,
    )


def test_tick_wraps_exact_service_execution_and_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = RecordingPolicy(EMPTY_RESULT)
    context = make_context()
    journal = EventJournal()
    expected = make_execution(context, EMPTY_RESULT, journal)
    calls: list[tuple[EMSPolicy, EnergySystemContext, EventJournal]] = []

    def fake_execute(
        supplied_policy: EMSPolicy,
        supplied_context: EnergySystemContext,
        supplied_journal: EventJournal,
    ) -> JournaledEMSCycle:
        calls.append((supplied_policy, supplied_context, supplied_journal))
        return expected

    monkeypatch.setattr(
        JournaledEMSExecutionService,
        "execute",
        staticmethod(fake_execute),
    )

    tick = JournaledEMSRuntime.tick(policy, context, journal)

    assert calls == [(policy, context, journal)]
    assert tick.execution is expected
    assert policy.calls == 0


def test_end_to_end_execution_preserves_nested_identities_and_runs_once() -> None:
    context = make_context()
    result = DecisionResult(events=(make_event(1),))
    policy = RecordingPolicy(result)

    tick = JournaledEMSRuntime.tick(policy, context, EventJournal())

    assert policy.calls == 1
    assert policy.received_context is context
    assert tick.execution.cycle.context is context
    assert tick.execution.cycle.result is result


def test_eventful_tick_progresses_journal_without_mutating_source() -> None:
    source = EventJournal()
    result = DecisionResult(events=(make_event(1), make_event(2)))

    tick = JournaledEMSRuntime.tick(
        RecordingPolicy(result),
        make_context(),
        source,
    )

    records = tick.execution.journal.events()
    assert source.events() == ()
    assert tick.execution.journal is not source
    assert tuple(record.sequence for record in records) == (0, 1)
    assert tuple(record.event for record in records) == result.events
    assert all(
        record.event is event
        for record, event in zip(records, result.events, strict=True)
    )


def test_empty_events_preserve_exact_source_journal_identity() -> None:
    source = EventJournal()

    tick = JournaledEMSRuntime.tick(
        RecordingPolicy(EMPTY_RESULT),
        make_context(),
        source,
    )

    assert tick.execution.journal is source


@pytest.mark.parametrize(
    ("policy", "context", "journal", "field_name"),
    [
        (
            cast(EMSPolicy, object()),
            make_context(),
            EventJournal(),
            "policy",
        ),
        (
            RecordingPolicy(EMPTY_RESULT),
            cast(EnergySystemContext, object()),
            EventJournal(),
            "context",
        ),
        (
            RecordingPolicy(EMPTY_RESULT),
            make_context(),
            cast(EventJournal, object()),
            "journal",
        ),
    ],
)
def test_invalid_inputs_are_rejected_before_service_delegation(
    monkeypatch: pytest.MonkeyPatch,
    policy: EMSPolicy,
    context: EnergySystemContext,
    journal: EventJournal,
    field_name: str,
) -> None:
    def fail_if_called(
        supplied_policy: EMSPolicy,
        supplied_context: EnergySystemContext,
        supplied_journal: EventJournal,
    ) -> JournaledEMSCycle:
        raise AssertionError("invalid input reached execution service")

    monkeypatch.setattr(
        JournaledEMSExecutionService,
        "execute",
        staticmethod(fail_if_called),
    )

    with pytest.raises(TypeError, match=field_name):
        JournaledEMSRuntime.tick(policy, context, journal)


def test_invalid_journal_is_rejected_before_policy_evaluation() -> None:
    policy = RecordingPolicy(EMPTY_RESULT)

    with pytest.raises(TypeError, match="journal"):
        JournaledEMSRuntime.tick(
            policy,
            make_context(),
            cast(EventJournal, object()),
        )

    assert policy.calls == 0


def test_policy_exception_identity_is_preserved() -> None:
    with pytest.raises(RuntimeError) as raised:
        JournaledEMSRuntime.tick(
            RaisingPolicy(),
            make_context(),
            EventJournal(),
        )

    assert raised.value is POLICY_ERROR


def test_service_exception_identity_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_from_service(
        policy: EMSPolicy,
        context: EnergySystemContext,
        journal: EventJournal,
    ) -> JournaledEMSCycle:
        raise SERVICE_ERROR

    monkeypatch.setattr(
        JournaledEMSExecutionService,
        "execute",
        staticmethod(raise_from_service),
    )

    with pytest.raises(RuntimeError) as raised:
        JournaledEMSRuntime.tick(
            RecordingPolicy(EMPTY_RESULT),
            make_context(),
            EventJournal(),
        )

    assert raised.value is SERVICE_ERROR


def test_journaled_tick_is_frozen_slotted_and_has_exact_field() -> None:
    execution = make_execution(make_context(), EMPTY_RESULT, EventJournal())
    tick = JournaledEMSTick(execution=execution)

    assert tuple(field.name for field in fields(JournaledEMSTick)) == ("execution",)
    assert JournaledEMSTick.__slots__ == ("execution",)
    assert not hasattr(tick, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, tick).execution = execution


def test_invalid_execution_is_rejected() -> None:
    with pytest.raises(TypeError, match="execution"):
        JournaledEMSTick(execution=cast(JournaledEMSCycle, object()))


def test_runtime_is_stateless_and_has_only_explicit_tick_dependencies() -> None:
    runtime = JournaledEMSRuntime()

    assert JournaledEMSRuntime.__slots__ == ()
    assert not hasattr(runtime, "__dict__")
    assert list(signature(JournaledEMSRuntime.tick).parameters) == [
        "policy",
        "context",
        "journal",
    ]
    with pytest.raises(AttributeError):
        cast(Any, runtime).policy = RecordingPolicy(EMPTY_RESULT)
