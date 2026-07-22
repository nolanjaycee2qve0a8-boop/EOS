"""Immutable observation of external facts at a specific time."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from kernel.domain.validation import (
    freeze_mapping,
    require_non_empty_string,
    require_timezone_aware,
)
from kernel.ids import AssetId, SnapshotId


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Facts observed for one asset at an explicitly supplied time."""

    snapshot_id: SnapshotId
    observed_at: datetime
    asset_id: AssetId
    values: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "snapshot_id",
            SnapshotId(require_non_empty_string(self.snapshot_id, "snapshot_id")),
        )
        object.__setattr__(
            self,
            "observed_at",
            require_timezone_aware(self.observed_at, "observed_at"),
        )
        object.__setattr__(
            self,
            "asset_id",
            AssetId(require_non_empty_string(self.asset_id, "asset_id")),
        )
        object.__setattr__(self, "values", freeze_mapping(self.values, "values"))
