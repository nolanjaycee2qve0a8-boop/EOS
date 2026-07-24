"""Tests for explicit deterministic journaled tick progression."""

from datetime import UTC, datetime
from inspect import signature
from typing import cast

import pytest

from kernel.context import EnergySystemContext
from kernel.cycle import EMSCycle, JournaledEMSCycle
from kernel.decision import DecisionResult
from kernel.domain import Event
from kernel.event import EventJournal
from kernel.ids import EventId
from kernel.policy import EMSPolicy
from kernel.power import PowerFlow
from kernel.runtime import JournaledEMSRuntime, JournaledEMSTick

FIXED_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
EMPTY_RESULT = DecisionResult.empty()
TICK_ERROR = RuntimeError("tick failed")
POLICY_ERROR = RuntimeError("policy failed")


def make_event(number: int) -> Event:
    return Event(
        event_id=EventId(f"progress-event-{number}"),
        event_type="decision_recorded",
        occurred_at=FIXED_TIME,
        recorded_at=FIXED_TIME,
        payload={"number": number},
    )


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


def make_tick(
    context: EnergySystemContext | None = None,
    result: DecisionResult = EMPTY_RESULT,
    journal: EventJournal | None = None,
) -> JournaledEMSTick:
    supplied_context = context if context is not None else make_context()
    supplied_journal = journal if journal is not None else EventJournal()
    return JournaledEMSTick(
        execution=JournaledEMSCycle(
            cycle=EMSCycle(context=supplied_context, result=result),
            journal=supplied_journal,
        )
    )


def test_progress_delegates_once_with_exact_inputs_and_returns_exact_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous = make_tick()
    policy = RecordingPolicy(EMPTY_RESULT)
    context = make_context(1.0)
    expected = make_tick(context=context)
    calls: list[tuple[EMSPolicy, EnergySystemContext, EventJournal]] = []

    def fake_tick(
        supplied_policy: EMSPolicy,
        supplied_context: EnergySystemContext,
        supplied_journal: EventJournal,
    ) -> JournaledEMSTick:
        calls.append((supplied_policy, supplied_context, supplied_journal))
        return expected

    monkeypatch.setattr(
        JournaledEMSRuntime,
        "tick",
        staticmethod(fake_tick),
    )

    actual = JournaledEMSRuntime.progress(previous, policy, context)

    assert calls == [(policy, context, previous.execution.journal)]
    assert actual is expected
    assert policy.calls == 0


def test_valid_progress_returns_journaled_tick_and_evaluates_once() -> None:
    previous = make_tick()
    policy = RecordingPolicy(DecisionResult(events=(make_event(1),)))
    context = make_context()

    progressed = JournaledEMSRuntime.progress(previous, policy, context)

    assert isinstance(progressed, JournaledEMSTick)
    assert policy.calls == 1
    assert policy.contexts == [context]


def test_progress_does_not_change_previous_tick_or_journal() -> None:
    previous = JournaledEMSRuntime.tick(
        RecordingPolicy(DecisionResult(events=(make_event(1),))),
        make_context(),
        EventJournal(),
    )
    source_journal = previous.execution.journal
    source_records = source_journal.events()

    progressed = JournaledEMSRuntime.progress(
        previous,
        RecordingPolicy(DecisionResult(events=(make_event(2),))),
        make_context(),
    )

    assert previous.execution.journal is source_journal
    assert source_journal.events() is source_records
    assert tuple(record.sequence for record in source_records) == (0,)
    assert progressed.execution.journal is not source_journal


def test_two_eventful_ticks_produce_contiguous_sequences() -> None:
    first_event = make_event(1)
    second_event = make_event(2)
    first = JournaledEMSRuntime.tick(
        RecordingPolicy(DecisionResult(events=(first_event,))),
        make_context(),
        EventJournal(),
    )

    second = JournaledEMSRuntime.progress(
        first,
        RecordingPolicy(DecisionResult(events=(second_event,))),
        make_context(),
    )

    records = second.execution.journal.events()
    assert tuple(record.sequence for record in records) == (0, 1)
    assert records[0] is first.execution.journal.events()[0]
    assert records[0].event is first_event
    assert records[1].event is second_event


def test_three_ticks_continue_sequence_deterministically() -> None:
    first = JournaledEMSRuntime.tick(
        RecordingPolicy(DecisionResult(events=(make_event(1),))),
        make_context(),
        EventJournal(),
    )
    second = JournaledEMSRuntime.progress(
        first,
        RecordingPolicy(DecisionResult(events=(make_event(2),))),
        make_context(),
    )
    third = JournaledEMSRuntime.progress(
        second,
        RecordingPolicy(DecisionResult(events=(make_event(3),))),
        make_context(),
    )

    assert tuple(record.sequence for record in third.execution.journal.events()) == (
        0,
        1,
        2,
    )


def test_multiple_events_continue_from_previous_last_sequence() -> None:
    first = JournaledEMSRuntime.tick(
        RecordingPolicy(DecisionResult(events=(make_event(1), make_event(2)))),
        make_context(),
        EventJournal(),
    )
    new_events = (make_event(3), make_event(4), make_event(5))

    second = JournaledEMSRuntime.progress(
        first,
        RecordingPolicy(DecisionResult(events=new_events)),
        make_context(),
    )

    records = second.execution.journal.events()
    assert tuple(record.sequence for record in records) == (0, 1, 2, 3, 4)
    assert all(
        record.event is event
        for record, event in zip(records[-3:], new_events, strict=True)
    )


def test_empty_progress_preserves_journal_and_consumes_no_sequence() -> None:
    first = JournaledEMSRuntime.tick(
        RecordingPolicy(DecisionResult(events=(make_event(1),))),
        make_context(),
        EventJournal(),
    )

    empty = JournaledEMSRuntime.progress(
        first,
        RecordingPolicy(EMPTY_RESULT),
        make_context(),
    )

    assert empty.execution.journal is first.execution.journal
    assert tuple(record.sequence for record in empty.execution.journal.events()) == (0,)


def test_event_after_empty_progress_uses_actual_next_sequence() -> None:
    first = JournaledEMSRuntime.tick(
        RecordingPolicy(DecisionResult(events=(make_event(1),))),
        make_context(),
        EventJournal(),
    )
    empty = JournaledEMSRuntime.progress(
        first,
        RecordingPolicy(EMPTY_RESULT),
        make_context(),
    )
    later_event = make_event(2)

    later = JournaledEMSRuntime.progress(
        empty,
        RecordingPolicy(DecisionResult(events=(later_event,))),
        make_context(),
    )

    records = later.execution.journal.events()
    assert tuple(record.sequence for record in records) == (0, 1)
    assert records[0] is first.execution.journal.events()[0]
    assert records[1].event is later_event


def test_different_ticks_accept_different_policies_and_contexts() -> None:
    first_context = make_context()
    second_context = make_context(2.0)
    first_policy = RecordingPolicy(EMPTY_RESULT)
    second_policy = RecordingPolicy(EMPTY_RESULT)
    first = JournaledEMSRuntime.tick(
        first_policy,
        first_context,
        EventJournal(),
    )

    second = JournaledEMSRuntime.progress(
        first,
        second_policy,
        second_context,
    )

    assert first_policy.contexts == [first_context]
    assert second_policy.contexts == [second_context]
    assert second.execution.cycle.context is second_context


@pytest.mark.parametrize(
    ("previous_tick", "policy", "context", "field_name"),
    [
        (
            cast(JournaledEMSTick, object()),
            RecordingPolicy(EMPTY_RESULT),
            make_context(),
            "previous_tick",
        ),
        (
            make_tick(),
            cast(EMSPolicy, object()),
            make_context(),
            "policy",
        ),
        (
            make_tick(),
            RecordingPolicy(EMPTY_RESULT),
            cast(EnergySystemContext, object()),
            "context",
        ),
    ],
)
def test_invalid_inputs_fail_before_tick_delegation(
    monkeypatch: pytest.MonkeyPatch,
    previous_tick: JournaledEMSTick,
    policy: EMSPolicy,
    context: EnergySystemContext,
    field_name: str,
) -> None:
    def fail_if_called(
        supplied_policy: EMSPolicy,
        supplied_context: EnergySystemContext,
        supplied_journal: EventJournal,
    ) -> JournaledEMSTick:
        raise AssertionError("invalid input reached tick")

    monkeypatch.setattr(
        JournaledEMSRuntime,
        "tick",
        staticmethod(fail_if_called),
    )

    with pytest.raises(TypeError, match=field_name):
        JournaledEMSRuntime.progress(previous_tick, policy, context)


def test_tick_exception_identity_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_from_tick(
        policy: EMSPolicy,
        context: EnergySystemContext,
        journal: EventJournal,
    ) -> JournaledEMSTick:
        raise TICK_ERROR

    monkeypatch.setattr(
        JournaledEMSRuntime,
        "tick",
        staticmethod(raise_from_tick),
    )

    with pytest.raises(RuntimeError) as raised:
        JournaledEMSRuntime.progress(
            make_tick(),
            RecordingPolicy(EMPTY_RESULT),
            make_context(),
        )

    assert raised.value is TICK_ERROR


def test_policy_exception_identity_and_failed_progress_immutability() -> None:
    previous = JournaledEMSRuntime.tick(
        RecordingPolicy(DecisionResult(events=(make_event(1),))),
        make_context(),
        EventJournal(),
    )
    journal = previous.execution.journal
    records = journal.events()

    with pytest.raises(RuntimeError) as raised:
        JournaledEMSRuntime.progress(
            previous,
            RaisingPolicy(),
            make_context(),
        )

    assert raised.value is POLICY_ERROR
    assert previous.execution.journal is journal
    assert journal.events() is records


def test_progress_signature_contains_only_explicit_dependencies() -> None:
    assert list(signature(JournaledEMSRuntime.progress).parameters) == [
        "previous_tick",
        "policy",
        "context",
    ]
