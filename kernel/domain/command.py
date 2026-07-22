"""Immutable decision requesting an action from an asset."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from kernel.domain.validation import (
    freeze_mapping,
    require_non_empty_string,
    require_timezone_aware,
)
from kernel.ids import AssetId, CommandId, MissionId, SnapshotId


@dataclass(frozen=True, slots=True)
class Command:
    """An action selected from one mission and one observed snapshot."""

    command_id: CommandId
    mission_id: MissionId
    snapshot_id: SnapshotId
    asset_id: AssetId
    issued_at: datetime
    action: str
    parameters: Mapping[str, object]

    def __post_init__(self) -> None:
        id_fields = (
            ("command_id", CommandId),
            ("mission_id", MissionId),
            ("snapshot_id", SnapshotId),
            ("asset_id", AssetId),
        )
        for field_name, id_type in id_fields:
            value = require_non_empty_string(getattr(self, field_name), field_name)
            object.__setattr__(self, field_name, id_type(value))
        object.__setattr__(
            self,
            "issued_at",
            require_timezone_aware(self.issued_at, "issued_at"),
        )
        object.__setattr__(
            self,
            "action",
            require_non_empty_string(self.action, "action"),
        )
        object.__setattr__(
            self,
            "parameters",
            freeze_mapping(self.parameters, "parameters"),
        )
