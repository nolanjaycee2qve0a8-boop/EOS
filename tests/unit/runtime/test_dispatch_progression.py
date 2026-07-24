"""Tests for explicit progression after a completed dispatch phase."""

from datetime import UTC, datetime
from inspect import signature
from typing import cast

import pytest

from kernel.context import EnergySystemContext
from kernel.cycle import EMSCycle, JournaledEMSCycle
from kernel.decision import DecisionResult
from kernel.dispatch import CommandDispatcher, CommandExecutor
from kernel.domain import Event
from kernel.event import EventJournal
from kernel.ids import EventId
from kernel.policy import EMSPolicy
from kernel.power import PowerFlow
from kernel.runtime import (
    DispatchedJournaledEMSTick,
    JournaledEMSRuntime,
    JournaledEMSTick,
)

FIXED_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
PROGRESS_ERROR = RuntimeError("progress failed")
POLICY_ERROR = RuntimeError("policy failed")


def make_event(number: int) -> Event:
    return Event(
        event_id=EventId(f"dispatch-progress-event-{number}"),
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


class RecordingDispatcher(CommandDispatcher):
    __slots__ = ("calls",)

    def __init__(self) -> None:
        self.calls = 0

    def dispatch(self, command: object) -> None:
        self.calls += 1


def make_tick(
    result: DecisionResult | None = None,
    journal: EventJournal | None = None,
) -> JournaledEMSTick:
    supplied_result = result if result is not None else DecisionResult.empty()
    supplied_journal = journal if journal is not None else EventJournal()
    return JournaledEMSTick(
        execution=JournaledEMSCycle(
            cycle=EMSCycle(
                context=make_context(),
                result=supplied_result,
            ),
            journal=supplied_journal,
        )
    )


def make_dispatched(tick: JournaledEMSTick | None = None) -> DispatchedJournaledEMSTick:
    return DispatchedJournaledEMSTick(tick=tick if tick is not None else make_tick())


def test_delegates_once_with_exact_inputs_and_returns_exact_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous = make_dispatched()
    policy = RecordingPolicy(DecisionResult.empty())
    context = make_context(1.0)
    expected = make_tick()
    calls: list[tuple[JournaledEMSTick, EMSPolicy, EnergySystemContext]] = []

    def fake_progress(
        supplied_tick: JournaledEMSTick,
        supplied_policy: EMSPolicy,
        supplied_context: EnergySystemContext,
    ) -> JournaledEMSTick:
        calls.append((supplied_tick, supplied_policy, supplied_context))
        return expected

    def fail_if_tick_called(
        supplied_policy: EMSPolicy,
        supplied_context: EnergySystemContext,
        journal: EventJournal,
    ) -> JournaledEMSTick:
        raise AssertionError("progress_after_dispatch called tick directly")

    def fail_if_dispatch_called(
        tick: JournaledEMSTick,
        dispatcher: CommandDispatcher,
    ) -> DispatchedJournaledEMSTick:
        raise AssertionError("progress_after_dispatch repeated dispatch")

    def fail_if_executor_called(
        dispatcher: CommandDispatcher,
        result: DecisionResult,
    ) -> None:
        raise AssertionError("progress_after_dispatch called CommandExecutor")

    monkeypatch.setattr(
        JournaledEMSRuntime,
        "progress",
        staticmethod(fake_progress),
    )
    monkeypatch.setattr(
        JournaledEMSRuntime,
        "tick",
        staticmethod(fail_if_tick_called),
    )
    monkeypatch.setattr(
        JournaledEMSRuntime,
        "dispatch",
        staticmethod(fail_if_dispatch_called),
    )
    monkeypatch.setattr(
        CommandExecutor,
        "execute",
        staticmethod(fail_if_executor_called),
    )

    actual = JournaledEMSRuntime.progress_after_dispatch(
        previous,
        policy,
        context,
    )

    assert calls == [(previous.tick, policy, context)]
    assert actual is expected
    assert policy.calls == 0


def test_next_tick_continues_exact_journal_and_event_sequence() -> None:
    first_event = make_event(1)
    next_event = make_event(2)
    first = JournaledEMSRuntime.tick(
        RecordingPolicy(DecisionResult(events=(first_event,))),
        make_context(),
        EventJournal(),
    )
    source_journal = first.execution.journal
    source_record = source_journal.events()[0]
    dispatcher = RecordingDispatcher()
    dispatched = JournaledEMSRuntime.dispatch(first, dispatcher)
    next_policy = RecordingPolicy(DecisionResult(events=(next_event,)))

    next_tick = JournaledEMSRuntime.progress_after_dispatch(
        dispatched,
        next_policy,
        make_context(2.0),
    )

    records = next_tick.execution.journal.events()
    assert dispatcher.calls == 0
    assert tuple(record.sequence for record in records) == (0, 1)
    assert records[0] is source_record
    assert records[0].event is first_event
    assert records[1].event is next_event
    assert dispatched.tick is first
    assert first.execution.journal is source_journal
    assert next_policy.calls == 1


def test_no_command_dispatch_is_valid_for_progression() -> None:
    first = JournaledEMSRuntime.tick(
        RecordingPolicy(DecisionResult.empty()),
        make_context(),
        EventJournal(),
    )
    dispatcher = RecordingDispatcher()
    dispatched = JournaledEMSRuntime.dispatch(first, dispatcher)

    next_tick = JournaledEMSRuntime.progress_after_dispatch(
        dispatched,
        RecordingPolicy(DecisionResult(events=(make_event(1),))),
        make_context(),
    )

    assert dispatcher.calls == 0
    assert next_tick.execution.journal.events()[0].sequence == 0


def test_empty_event_progression_preserves_exact_journal_identity() -> None:
    first = JournaledEMSRuntime.tick(
        RecordingPolicy(DecisionResult(events=(make_event(1),))),
        make_context(),
        EventJournal(),
    )
    dispatched = JournaledEMSRuntime.dispatch(first, RecordingDispatcher())

    next_tick = JournaledEMSRuntime.progress_after_dispatch(
        dispatched,
        RecordingPolicy(DecisionResult.empty()),
        make_context(),
    )

    assert next_tick.execution.journal is first.execution.journal


def test_different_policy_and_context_are_used_exactly_once() -> None:
    first_policy = RecordingPolicy(DecisionResult.empty())
    first_context = make_context()
    first = JournaledEMSRuntime.tick(
        first_policy,
        first_context,
        EventJournal(),
    )
    dispatched = JournaledEMSRuntime.dispatch(first, RecordingDispatcher())
    next_policy = RecordingPolicy(DecisionResult.empty())
    next_context = make_context(3.0)

    next_tick = JournaledEMSRuntime.progress_after_dispatch(
        dispatched,
        next_policy,
        next_context,
    )

    assert first_policy.contexts == [first_context]
    assert next_policy.contexts == [next_context]
    assert next_tick.execution.cycle.context is next_context


@pytest.mark.parametrize(
    ("previous_dispatch", "policy", "context", "field_name"),
    [
        (
            cast(DispatchedJournaledEMSTick, object()),
            RecordingPolicy(DecisionResult.empty()),
            make_context(),
            "previous_dispatch",
        ),
        (
            cast(DispatchedJournaledEMSTick, make_tick()),
            RecordingPolicy(DecisionResult.empty()),
            make_context(),
            "previous_dispatch",
        ),
        (
            make_dispatched(),
            cast(EMSPolicy, object()),
            make_context(),
            "policy",
        ),
        (
            make_dispatched(),
            RecordingPolicy(DecisionResult.empty()),
            cast(EnergySystemContext, object()),
            "context",
        ),
    ],
)
def test_invalid_inputs_fail_before_progress_delegation(
    monkeypatch: pytest.MonkeyPatch,
    previous_dispatch: DispatchedJournaledEMSTick,
    policy: EMSPolicy,
    context: EnergySystemContext,
    field_name: str,
) -> None:
    def fail_if_called(
        tick: JournaledEMSTick,
        supplied_policy: EMSPolicy,
        supplied_context: EnergySystemContext,
    ) -> JournaledEMSTick:
        raise AssertionError("invalid input reached progress")

    monkeypatch.setattr(
        JournaledEMSRuntime,
        "progress",
        staticmethod(fail_if_called),
    )

    with pytest.raises(TypeError, match=field_name):
        JournaledEMSRuntime.progress_after_dispatch(
            previous_dispatch,
            policy,
            context,
        )


def test_progress_exception_identity_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_from_progress(
        tick: JournaledEMSTick,
        policy: EMSPolicy,
        context: EnergySystemContext,
    ) -> JournaledEMSTick:
        raise PROGRESS_ERROR

    monkeypatch.setattr(
        JournaledEMSRuntime,
        "progress",
        staticmethod(raise_from_progress),
    )

    with pytest.raises(RuntimeError) as raised:
        JournaledEMSRuntime.progress_after_dispatch(
            make_dispatched(),
            RecordingPolicy(DecisionResult.empty()),
            make_context(),
        )

    assert raised.value is PROGRESS_ERROR


def test_policy_exception_preserves_previous_dispatch_and_journal() -> None:
    first = JournaledEMSRuntime.tick(
        RecordingPolicy(DecisionResult(events=(make_event(1),))),
        make_context(),
        EventJournal(),
    )
    dispatched = JournaledEMSRuntime.dispatch(first, RecordingDispatcher())
    journal = first.execution.journal
    records = journal.events()

    with pytest.raises(RuntimeError) as raised:
        JournaledEMSRuntime.progress_after_dispatch(
            dispatched,
            RaisingPolicy(),
            make_context(),
        )

    assert raised.value is POLICY_ERROR
    assert dispatched.tick is first
    assert first.execution.journal is journal
    assert journal.events() is records


def test_existing_progress_remains_usable() -> None:
    previous = make_tick()
    policy = RecordingPolicy(DecisionResult.empty())
    context = make_context()

    next_tick = JournaledEMSRuntime.progress(previous, policy, context)

    assert isinstance(next_tick, JournaledEMSTick)
    assert policy.calls == 1


def test_progress_after_dispatch_signature_is_explicit() -> None:
    assert list(signature(JournaledEMSRuntime.progress_after_dispatch).parameters) == [
        "previous_dispatch",
        "policy",
        "context",
    ]
