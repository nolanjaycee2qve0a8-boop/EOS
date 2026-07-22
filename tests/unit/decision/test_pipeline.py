"""Tests for deterministic single-call DecisionPipeline orchestration."""

from datetime import UTC, datetime
from typing import cast

import pytest

from kernel.decision import DecisionPipeline, DecisionPolicy, DecisionResult
from kernel.domain import Command, Event, Mission, Snapshot
from kernel.ids import (
    AssetId,
    CommandId,
    EventId,
    MissionId,
    SnapshotId,
)

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


def make_command(number: int) -> Command:
    return Command(
        command_id=CommandId(f"command-{number}"),
        mission_id=MissionId("mission-1"),
        snapshot_id=SnapshotId("snapshot-1"),
        asset_id=AssetId("asset-1"),
        issued_at=FIXED_TIME,
        action="set_power",
        parameters={"power_kw": number},
    )


def make_event(number: int) -> Event:
    return Event(
        event_id=EventId(f"event-{number}"),
        event_type="command_issued",
        occurred_at=FIXED_TIME,
        recorded_at=FIXED_TIME,
        payload={"sequence": number},
    )


class EmptyPolicy:
    def decide(self, snapshot: Snapshot, mission: Mission) -> DecisionResult:
        return DecisionResult.empty()


class RecordingPolicy:
    def __init__(self, result: DecisionResult) -> None:
        self.result = result
        self.calls = 0
        self.received_snapshot: Snapshot | None = None
        self.received_mission: Mission | None = None

    def decide(self, snapshot: Snapshot, mission: Mission) -> DecisionResult:
        self.calls += 1
        self.received_snapshot = snapshot
        self.received_mission = mission
        return self.result


class RaisingPolicy:
    def __init__(self, error: RuntimeError) -> None:
        self.error = error

    def decide(self, snapshot: Snapshot, mission: Mission) -> DecisionResult:
        raise self.error


class InvalidReturnPolicy:
    def decide(self, snapshot: Snapshot, mission: Mission) -> DecisionResult:
        return cast(DecisionResult, [])


def test_pipeline_executes_policy_and_returns_result() -> None:
    expected = DecisionResult([make_command(1)], [make_event(1)])
    assert (
        DecisionPipeline(RecordingPolicy(expected)).execute(
            make_snapshot(), make_mission()
        )
        == expected
    )


def test_pipeline_calls_policy_exactly_once() -> None:
    policy = RecordingPolicy(DecisionResult.empty())
    DecisionPipeline(policy).execute(make_snapshot(), make_mission())
    assert policy.calls == 1


def test_pipeline_passes_exact_snapshot() -> None:
    snapshot = make_snapshot()
    policy = RecordingPolicy(DecisionResult.empty())
    DecisionPipeline(policy).execute(snapshot, make_mission())
    assert policy.received_snapshot is snapshot


def test_pipeline_passes_exact_mission() -> None:
    mission = make_mission()
    policy = RecordingPolicy(DecisionResult.empty())
    DecisionPipeline(policy).execute(make_snapshot(), mission)
    assert policy.received_mission is mission


def test_pipeline_returns_exact_policy_result() -> None:
    expected = DecisionResult.empty()
    actual = DecisionPipeline(RecordingPolicy(expected)).execute(
        make_snapshot(), make_mission()
    )
    assert actual is expected


def test_pipeline_supports_empty_result() -> None:
    result = DecisionPipeline(EmptyPolicy()).execute(make_snapshot(), make_mission())
    assert result == DecisionResult.empty()


def test_pipeline_preserves_multiple_output_order() -> None:
    command_1, command_2 = make_command(1), make_command(2)
    event_1, event_2 = make_event(1), make_event(2)
    expected = DecisionResult([command_2, command_1], [event_2, event_1])
    actual = DecisionPipeline(RecordingPolicy(expected)).execute(
        make_snapshot(), make_mission()
    )
    assert actual.commands == (command_2, command_1)
    assert actual.events == (event_2, event_1)


def test_pipeline_rejects_invalid_snapshot() -> None:
    snapshot = cast(Snapshot, object())
    with pytest.raises(TypeError, match="snapshot"):
        DecisionPipeline(EmptyPolicy()).execute(snapshot, make_mission())


def test_pipeline_rejects_invalid_mission() -> None:
    mission = cast(Mission, object())
    with pytest.raises(TypeError, match="mission"):
        DecisionPipeline(EmptyPolicy()).execute(make_snapshot(), mission)


def test_pipeline_rejects_invalid_policy() -> None:
    policy = cast(DecisionPolicy, object())
    with pytest.raises(TypeError, match="policy"):
        DecisionPipeline(policy)


def test_pipeline_rejects_invalid_policy_result() -> None:
    with pytest.raises(TypeError, match="DecisionResult"):
        DecisionPipeline(InvalidReturnPolicy()).execute(make_snapshot(), make_mission())


def test_pipeline_propagates_policy_exception_unchanged() -> None:
    expected = RuntimeError("policy failed")
    with pytest.raises(RuntimeError) as raised:
        DecisionPipeline(RaisingPolicy(expected)).execute(
            make_snapshot(), make_mission()
        )
    assert raised.value is expected


def test_pipeline_does_not_mutate_snapshot() -> None:
    snapshot = make_snapshot()
    expected = make_snapshot()
    DecisionPipeline(EmptyPolicy()).execute(snapshot, make_mission())
    assert snapshot == expected


def test_pipeline_does_not_mutate_mission() -> None:
    mission = make_mission()
    expected = make_mission()
    DecisionPipeline(EmptyPolicy()).execute(make_snapshot(), mission)
    assert mission == expected


def test_pipeline_does_not_generate_extra_commands() -> None:
    command = make_command(1)
    result = DecisionPipeline(RecordingPolicy(DecisionResult([command]))).execute(
        make_snapshot(), make_mission()
    )
    assert result.commands == (command,)


def test_pipeline_does_not_generate_extra_events() -> None:
    event = make_event(1)
    result = DecisionPipeline(RecordingPolicy(DecisionResult(events=[event]))).execute(
        make_snapshot(), make_mission()
    )
    assert result.events == (event,)
