"""Immutable intent for an EOS decision horizon."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from kernel.domain.validation import (
    freeze_mapping,
    require_non_empty_string,
    require_non_negative_integer,
    require_timezone_aware,
)
from kernel.ids import MissionId


@dataclass(frozen=True, slots=True)
class Mission:
    """An objective and its constraints over an explicit validity interval."""

    mission_id: MissionId
    created_at: datetime
    valid_from: datetime
    valid_until: datetime | None
    objective: str
    priority: int
    parameters: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "mission_id",
            MissionId(require_non_empty_string(self.mission_id, "mission_id")),
        )
        object.__setattr__(
            self,
            "created_at",
            require_timezone_aware(self.created_at, "created_at"),
        )
        object.__setattr__(
            self,
            "valid_from",
            require_timezone_aware(self.valid_from, "valid_from"),
        )
        if self.valid_until is not None:
            valid_until = require_timezone_aware(self.valid_until, "valid_until")
            if valid_until <= self.valid_from:
                raise ValueError("valid_until must be later than valid_from")
            object.__setattr__(self, "valid_until", valid_until)
        object.__setattr__(
            self,
            "objective",
            require_non_empty_string(self.objective, "objective"),
        )
        object.__setattr__(
            self,
            "priority",
            require_non_negative_integer(self.priority, "priority"),
        )
        object.__setattr__(
            self,
            "parameters",
            freeze_mapping(self.parameters, "parameters"),
        )
