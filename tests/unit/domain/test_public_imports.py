"""Tests for the public domain and identity import surfaces."""

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


def test_domain_objects_are_publicly_importable() -> None:
    assert [item.__name__ for item in (Snapshot, Mission, Command, Event)] == [
        "Snapshot",
        "Mission",
        "Command",
        "Event",
    ]


def test_identity_types_are_publicly_importable() -> None:
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
