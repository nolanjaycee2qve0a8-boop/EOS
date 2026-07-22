"""Immutable outputs produced by one deterministic policy decision."""

from collections.abc import Iterable
from dataclasses import dataclass

from kernel.decision.validation import require_typed_iterable
from kernel.domain import Command, Event


@dataclass(frozen=True, slots=True, init=False)
class DecisionResult:
    """Ordered immutable commands and events returned by a decision policy."""

    commands: tuple[Command, ...]
    events: tuple[Event, ...]

    def __init__(
        self,
        commands: Iterable[Command] = (),
        events: Iterable[Event] = (),
    ) -> None:
        object.__setattr__(
            self,
            "commands",
            require_typed_iterable(commands, Command, "commands"),
        )
        object.__setattr__(
            self,
            "events",
            require_typed_iterable(events, Event, "events"),
        )

    @classmethod
    def empty(cls) -> "DecisionResult":
        """Return an immutable result containing no commands or events."""
        return cls()
