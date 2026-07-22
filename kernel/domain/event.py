"""Immutable record of a fact that has already occurred."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from kernel.domain.validation import (
    freeze_mapping,
    require_non_empty_string,
    require_timezone_aware,
)
from kernel.ids import CausationId, CorrelationId, EventId


@dataclass(frozen=True, slots=True)
class Event:
    """A recorded fact with optional correlation and causation context."""

    event_id: EventId
    event_type: str
    occurred_at: datetime
    recorded_at: datetime
    payload: Mapping[str, object]
    correlation_id: CorrelationId | None = None
    causation_id: CausationId | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "event_id",
            EventId(require_non_empty_string(self.event_id, "event_id")),
        )
        object.__setattr__(
            self,
            "event_type",
            require_non_empty_string(self.event_type, "event_type"),
        )
        object.__setattr__(
            self,
            "occurred_at",
            require_timezone_aware(self.occurred_at, "occurred_at"),
        )
        object.__setattr__(
            self,
            "recorded_at",
            require_timezone_aware(self.recorded_at, "recorded_at"),
        )
        if self.recorded_at < self.occurred_at:
            raise ValueError("recorded_at must not be earlier than occurred_at")
        object.__setattr__(self, "payload", freeze_mapping(self.payload, "payload"))
        if self.correlation_id is not None:
            object.__setattr__(
                self,
                "correlation_id",
                CorrelationId(
                    require_non_empty_string(self.correlation_id, "correlation_id")
                ),
            )
        if self.causation_id is not None:
            object.__setattr__(
                self,
                "causation_id",
                CausationId(
                    require_non_empty_string(self.causation_id, "causation_id")
                ),
            )
