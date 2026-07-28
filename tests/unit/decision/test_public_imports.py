"""Tests for public decision imports and TASK-002 import regression."""

from kernel.decision import (
    DecisionContext,
    DecisionContextResult,
    DecisionPipeline,
    DecisionPolicy,
    DecisionResult,
)
from kernel.domain import Command, Event, Mission, Snapshot
from kernel.ids import (
    AssetId,
    CausationId,
    CommandId,
    CorrelationId,
    EventId,
    MissionId,
    SnapshotId,
)


def test_decision_interfaces_are_publicly_importable() -> None:
    assert DecisionContext.__name__ == "DecisionContext"
    assert DecisionContextResult.__name__ == "DecisionContextResult"
    assert DecisionPipeline.__name__ == "DecisionPipeline"
    assert DecisionPolicy.__name__ == "DecisionPolicy"
    assert DecisionResult.__name__ == "DecisionResult"


def test_task_002_domain_imports_remain_public() -> None:
    assert [item.__name__ for item in (Snapshot, Mission, Command, Event)] == [
        "Snapshot",
        "Mission",
        "Command",
        "Event",
    ]


def test_task_002_id_imports_remain_public() -> None:
    values = (
        SnapshotId("snapshot-1"),
        MissionId("mission-1"),
        CommandId("command-1"),
        EventId("event-1"),
        AssetId("asset-1"),
        CorrelationId("correlation-1"),
        CausationId("causation-1"),
    )
    assert all(isinstance(value, str) for value in values)
