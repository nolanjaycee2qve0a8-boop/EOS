"""Tests for stateless journaled EMS execution orchestration."""

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

FIXED_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
EMPTY_RESULT = DecisionResult.empty()
POLICY_ERROR = RuntimeError("policy failed")
EMS_CYCLE_ERROR = RuntimeError("cycle execution failed")
JOURNALED_CYCLE_ERROR = RuntimeError("cycle recording failed")


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


class EmptyPolicy(EMSPolicy):
    __slots__ = ()

    def evaluate(self, context: EnergySystemContext) -> DecisionResult:
        return EMPTY_RESULT


class EventfulPolicy(EMSPolicy):
    __slots__ = ()

    def evaluate(self, context: EnergySystemContext) -> DecisionResult:
        return DecisionResult(events=(make_event(1), make_event(2)))


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


class DirectEvaluationFailsPolicy(EMSPolicy):
    __slots__ = ()

    def evaluate(self, context: EnergySystemContext) -> DecisionResult:
        raise AssertionError("service called policy.evaluate directly")


def test_valid_journaled_execution() -> None:
    result = JournaledEMSExecutionService.execute(
        EventfulPolicy(),
        make_context(),
        EventJournal(),
    )

    assert isinstance(result, JournaledEMSCycle)
    assert len(result.journal.events()) == 2


def test_exact_delegation_and_delegate_call_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = DirectEvaluationFailsPolicy()
    context = make_context()
    journal = EventJournal()
    cycle = EMSCycle(context=context, result=EMPTY_RESULT)
    expected = JournaledEMSCycle(cycle=cycle, journal=journal)
    cycle_calls: list[tuple[EMSPolicy, EnergySystemContext]] = []
    record_calls: list[tuple[EMSCycle, EventJournal]] = []

    def fake_cycle_execute(
        supplied_policy: EMSPolicy,
        supplied_context: EnergySystemContext,
    ) -> EMSCycle:
        cycle_calls.append((supplied_policy, supplied_context))
        return cycle

    def fake_record(
        supplied_cycle: EMSCycle,
        supplied_journal: EventJournal,
    ) -> JournaledEMSCycle:
        record_calls.append((supplied_cycle, supplied_journal))
        return expected

    monkeypatch.setattr(
        EMSCycle,
        "execute",
        staticmethod(fake_cycle_execute),
    )
    monkeypatch.setattr(
        JournaledEMSCycle,
        "record",
        staticmethod(fake_record),
    )

    actual = JournaledEMSExecutionService.execute(policy, context, journal)

    assert cycle_calls == [(policy, context)]
    assert record_calls == [(cycle, journal)]
    assert actual is expected


def test_policy_is_evaluated_exactly_once() -> None:
    policy = RecordingPolicy(EMPTY_RESULT)
    context = make_context()

    JournaledEMSExecutionService.execute(
        policy,
        context,
        EventJournal(),
    )

    assert policy.calls == 1
    assert policy.received_context is context


def test_preserves_context_and_decision_result_identities() -> None:
    context = make_context()
    result = DecisionResult(events=(make_event(1),))
    policy = RecordingPolicy(result)

    journaled = JournaledEMSExecutionService.execute(
        policy,
        context,
        EventJournal(),
    )

    assert journaled.cycle.context is context
    assert journaled.cycle.result is result


def test_eventful_result_progresses_journal() -> None:
    source = EventJournal()

    journaled = JournaledEMSExecutionService.execute(
        EventfulPolicy(),
        make_context(),
        source,
    )

    records = journaled.journal.events()
    assert journaled.journal is not source
    assert tuple(record.sequence for record in records) == (0, 1)
    assert tuple(record.event for record in records) == journaled.cycle.result.events


def test_empty_events_preserve_source_journal_identity() -> None:
    source = EventJournal()

    journaled = JournaledEMSExecutionService.execute(
        EmptyPolicy(),
        make_context(),
        source,
    )

    assert journaled.journal is source


def test_policy_exception_identity_is_preserved() -> None:
    with pytest.raises(RuntimeError) as raised:
        JournaledEMSExecutionService.execute(
            RaisingPolicy(),
            make_context(),
            EventJournal(),
        )

    assert raised.value is POLICY_ERROR


def test_ems_cycle_exception_identity_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_from_cycle(
        policy: EMSPolicy,
        context: EnergySystemContext,
    ) -> EMSCycle:
        raise EMS_CYCLE_ERROR

    monkeypatch.setattr(
        EMSCycle,
        "execute",
        staticmethod(raise_from_cycle),
    )

    with pytest.raises(RuntimeError) as raised:
        JournaledEMSExecutionService.execute(
            EmptyPolicy(),
            make_context(),
            EventJournal(),
        )

    assert raised.value is EMS_CYCLE_ERROR


def test_journaled_cycle_exception_identity_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_from_record(
        cycle: EMSCycle,
        journal: EventJournal,
    ) -> JournaledEMSCycle:
        raise JOURNALED_CYCLE_ERROR

    monkeypatch.setattr(
        JournaledEMSCycle,
        "record",
        staticmethod(raise_from_record),
    )

    with pytest.raises(RuntimeError) as raised:
        JournaledEMSExecutionService.execute(
            EmptyPolicy(),
            make_context(),
            EventJournal(),
        )

    assert raised.value is JOURNALED_CYCLE_ERROR


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
            EmptyPolicy(),
            cast(EnergySystemContext, object()),
            EventJournal(),
            "context",
        ),
        (
            EmptyPolicy(),
            make_context(),
            cast(EventJournal, object()),
            "journal",
        ),
    ],
)
def test_invalid_inputs_are_rejected_before_delegation(
    monkeypatch: pytest.MonkeyPatch,
    policy: EMSPolicy,
    context: EnergySystemContext,
    journal: EventJournal,
    field_name: str,
) -> None:
    def fail_if_delegated(
        supplied_policy: EMSPolicy,
        supplied_context: EnergySystemContext,
    ) -> EMSCycle:
        raise AssertionError("invalid input reached EMSCycle.execute")

    monkeypatch.setattr(
        EMSCycle,
        "execute",
        staticmethod(fail_if_delegated),
    )

    with pytest.raises(TypeError, match=field_name):
        JournaledEMSExecutionService.execute(policy, context, journal)


def test_invalid_journal_is_rejected_before_policy_evaluation() -> None:
    policy = RecordingPolicy(EMPTY_RESULT)

    with pytest.raises(TypeError, match="journal"):
        JournaledEMSExecutionService.execute(
            policy,
            make_context(),
            cast(EventJournal, object()),
        )

    assert policy.calls == 0


def test_service_is_stateless_and_has_no_instance_dictionary() -> None:
    service = JournaledEMSExecutionService()

    assert JournaledEMSExecutionService.__slots__ == ()
    assert not hasattr(service, "__dict__")
    with pytest.raises(AttributeError):
        cast(Any, service).policy = EmptyPolicy()


def test_execute_signature_contains_only_explicit_dependencies() -> None:
    assert list(signature(JournaledEMSExecutionService.execute).parameters) == [
        "policy",
        "context",
        "journal",
    ]
