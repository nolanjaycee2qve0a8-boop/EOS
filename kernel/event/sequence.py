"""Immutable sequence association for one domain event."""

from dataclasses import dataclass

from kernel.domain import Event
from kernel.event.validation import require_instance, require_sequence


@dataclass(frozen=True, slots=True)
class EventRecord:
    """Associate a caller-supplied sequence with an immutable domain event."""

    sequence: int
    event: Event

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "sequence",
            require_sequence(self.sequence, "sequence"),
        )
        object.__setattr__(
            self,
            "event",
            require_instance(self.event, Event, "event"),
        )
