"""Tests for deterministic RuntimeKernel orchestration."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from kernel.decision import DecisionPipeline, DecisionResult
from kernel.domain import Event, Mission, Snapshot
from kernel.event import EventJournal, EventRecord
from kernel.ids import AssetId, EventId, MissionId, SnapshotId
from kernel.runtime import RuntimeKernel

FIXED_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make_snapshot() -> Snapshot:
    return Snapshot(
        snapshot_id=SnapshotId("snapshot-1"),
        observed_at=FIXED_TIME,
        asset_id=AssetId("asset-1"),
        values={"power_kw": 5},
    )


def make_mission() -> Mission:
    return Mission(
        mission_id=MissionId("mission-1"),
        created_at=FIXED_TIME,
        valid_from=FIXED_TIME,
        valid_until=None,
        objective="maintain target power",
        priority=0,
        parameters={"target_kw": 5},
    )


def make_event(number: int) -> Event:
    return Event(
        event_id=EventId(f"event-{number}"),
        event_type="decision_recorded",
        occurred_at=FIXED_TIME,
        recorded_at=FIXED_TIME,
        payload={"number": number},
    )


class RecordingPolicy:
    def __init__(self, result: DecisionResult) -> None:
        self.result = result
        self.calls = 0
        self.snapshot: Snapshot | None = None
        self.mission: Mission | None = None

    def decide(self, snapshot: Snapshot, mission: Mission) -> DecisionResult:
        self.calls += 1
        self.snapshot = snapshot
        self.mission = mission
        return self.result


def make_kernel(
    decision_result: DecisionResult | None = None,
    journal: EventJournal | None = None,
) -> tuple[RuntimeKernel, RecordingPolicy]:
    policy = RecordingPolicy(decision_result or DecisionResult.empty())
    return (
        RuntimeKernel(
            pipeline=DecisionPipeline(policy),
            journal=journal or EventJournal(),
        ),
        policy,
    )


def test_runtime_kernel_accepts_pipeline_and_journal() -> None:
    pipeline = DecisionPipeline(RecordingPolicy(DecisionResult.empty()))
    journal = EventJournal()
    kernel = RuntimeKernel(pipeline, journal)
    assert kernel.pipeline is pipeline
    assert kernel.journal is journal


def test_tick_executes_one_decision() -> None:
    kernel, policy = make_kernel()
    result = kernel.tick(make_snapshot(), make_mission())
    assert result.decision_result is policy.result


def test_tick_calls_pipeline_policy_once() -> None:
    kernel, policy = make_kernel()
    kernel.tick(make_snapshot(), make_mission())
    assert policy.calls == 1


def test_tick_passes_exact_snapshot() -> None:
    snapshot = make_snapshot()
    kernel, policy = make_kernel()
    kernel.tick(snapshot, make_mission())
    assert policy.snapshot is snapshot


def test_tick_passes_exact_mission() -> None:
    mission = make_mission()
    kernel, policy = make_kernel()
    kernel.tick(make_snapshot(), mission)
    assert policy.mission is mission


def test_tick_preserves_decision_result_identity() -> None:
    expected = DecisionResult(events=[make_event(1)])
    kernel, _ = make_kernel(expected)
    assert kernel.tick(make_snapshot(), make_mission()).decision_result is expected


def test_tick_converts_events_to_event_records() -> None:
    event = make_event(1)
    kernel, _ = make_kernel(DecisionResult(events=[event]))
    records = kernel.tick(make_snapshot(), make_mission()).journal.events()
    assert records == (EventRecord(0, event),)


def test_empty_journal_sequence_starts_at_zero() -> None:
    event = make_event(1)
    kernel, _ = make_kernel(DecisionResult(events=[event]))
    record = kernel.tick(make_snapshot(), make_mission()).journal.events()[0]
    assert record.sequence == 0


def test_sequence_continues_from_existing_journal() -> None:
    existing = EventRecord(4, make_event(0))
    journal = EventJournal().append(existing)
    kernel, _ = make_kernel(DecisionResult(events=[make_event(1)]), journal)
    records = kernel.tick(make_snapshot(), make_mission()).journal.events()
    assert [record.sequence for record in records] == [4, 5]


def test_tick_preserves_event_order() -> None:
    first = make_event(1)
    second = make_event(2)
    kernel, _ = make_kernel(DecisionResult(events=[first, second]))
    records = kernel.tick(make_snapshot(), make_mission()).journal.events()
    assert [record.event for record in records] == [first, second]


def test_tick_preserves_event_identity() -> None:
    event = make_event(1)
    kernel, _ = make_kernel(DecisionResult(events=[event]))
    record = kernel.tick(make_snapshot(), make_mission()).journal.events()[0]
    assert record.event is event


def test_tick_leaves_old_journal_unchanged() -> None:
    existing = EventRecord(0, make_event(0))
    journal = EventJournal().append(existing)
    kernel, _ = make_kernel(DecisionResult(events=[make_event(1)]), journal)
    kernel.tick(make_snapshot(), make_mission())
    assert journal.events() == (existing,)


def test_tick_returns_new_journal_when_events_are_appended() -> None:
    journal = EventJournal()
    kernel, _ = make_kernel(DecisionResult(events=[make_event(1)]), journal)
    assert kernel.tick(make_snapshot(), make_mission()).journal is not journal


def test_tick_handles_empty_decision_events() -> None:
    journal = EventJournal()
    kernel, _ = make_kernel(DecisionResult.empty(), journal)
    assert kernel.tick(make_snapshot(), make_mission()).journal.events() == ()


def test_tick_rejects_invalid_snapshot_before_decision() -> None:
    kernel, policy = make_kernel()
    with pytest.raises(TypeError, match="snapshot"):
        kernel.tick(cast(Snapshot, object()), make_mission())
    assert policy.calls == 0


def test_tick_rejects_invalid_mission_before_decision() -> None:
    kernel, policy = make_kernel()
    with pytest.raises(TypeError, match="mission"):
        kernel.tick(make_snapshot(), cast(Mission, object()))
    assert policy.calls == 0


def test_runtime_kernel_rejects_invalid_pipeline() -> None:
    with pytest.raises(TypeError, match="pipeline"):
        RuntimeKernel(cast(DecisionPipeline, object()), EventJournal())


def test_runtime_kernel_rejects_invalid_journal() -> None:
    pipeline = DecisionPipeline(RecordingPolicy(DecisionResult.empty()))
    with pytest.raises(TypeError, match="journal"):
        RuntimeKernel(pipeline, cast(EventJournal, object()))


def test_runtime_kernel_is_frozen() -> None:
    kernel, _ = make_kernel()
    with pytest.raises(FrozenInstanceError):
        cast(Any, kernel).journal = EventJournal()


def test_runtime_kernel_uses_slots() -> None:
    kernel, _ = make_kernel()
    assert not hasattr(kernel, "__dict__")
