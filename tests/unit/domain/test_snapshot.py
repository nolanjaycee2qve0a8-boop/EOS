"""Tests for Snapshot."""

from collections.abc import MutableMapping
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from kernel.domain import Snapshot
from kernel.ids import AssetId, SnapshotId

FIXED_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make_snapshot(values: dict[str, object] | None = None) -> Snapshot:
    return Snapshot(
        snapshot_id=SnapshotId("snapshot-1"),
        observed_at=FIXED_TIME,
        asset_id=AssetId("asset-1"),
        values={} if values is None else values,
    )


def test_snapshot_creation() -> None:
    snapshot = make_snapshot({"power_kw": 4.5})
    assert snapshot.values["power_kw"] == 4.5


def test_snapshot_fields_are_frozen() -> None:
    snapshot = make_snapshot()
    with pytest.raises(FrozenInstanceError):
        cast(Any, snapshot).asset_id = AssetId("asset-2")


def test_snapshot_rejects_naive_observed_at() -> None:
    with pytest.raises(ValueError, match="observed_at"):
        Snapshot(
            SnapshotId("snapshot-1"),
            datetime(2026, 1, 1, 12, 0),
            AssetId("asset-1"),
            {},
        )


@pytest.mark.parametrize("snapshot_id", [SnapshotId(""), SnapshotId("  ")])
def test_snapshot_rejects_empty_id(snapshot_id: SnapshotId) -> None:
    with pytest.raises(ValueError, match="snapshot_id"):
        Snapshot(snapshot_id, FIXED_TIME, AssetId("asset-1"), {})


def test_snapshot_rejects_empty_asset_id() -> None:
    with pytest.raises(ValueError, match="asset_id"):
        Snapshot(SnapshotId("snapshot-1"), FIXED_TIME, AssetId(" "), {})


def test_snapshot_rejects_empty_values_key() -> None:
    with pytest.raises(ValueError, match="values"):
        make_snapshot({"": 1})


def test_snapshot_defensively_copies_values() -> None:
    values: dict[str, object] = {"power_kw": 4.5}
    snapshot = make_snapshot(values)
    values["power_kw"] = 9.0
    assert snapshot.values["power_kw"] == 4.5


def test_snapshot_values_are_read_only() -> None:
    values = cast(MutableMapping[str, object], make_snapshot().values)
    with pytest.raises(TypeError):
        values["power_kw"] = 1.0


def test_snapshot_value_equality() -> None:
    assert make_snapshot({"power_kw": 4.5}) == make_snapshot({"power_kw": 4.5})


def test_snapshot_repr_is_readable() -> None:
    assert "Snapshot" in repr(make_snapshot())
    assert "snapshot-1" in repr(make_snapshot())
