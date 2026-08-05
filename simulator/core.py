"""Immutable identity and time contract for one simulation step."""

from dataclasses import dataclass
from datetime import datetime

from simulator.validation import (
    require_optional_timezone_aware_datetime,
    require_positive_number,
    require_sequence,
)


@dataclass(frozen=True, slots=True)
class SimulationStepIdentity:
    """Identify one deterministic simulation step with explicit time facts.

    ``sequence`` is a required zero-based, non-negative step identity.
    ``duration_seconds`` is a required finite raw duration in seconds and must
    be greater than zero. ``timestamp`` is either the exact caller-supplied
    timezone-aware datetime or explicit ``None``. Construction never reads a
    clock, generates a timestamp or UUID, or advances a simulation.
    """

    sequence: int
    duration_seconds: float
    timestamp: datetime | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "sequence", require_sequence(self.sequence))
        object.__setattr__(
            self,
            "duration_seconds",
            require_positive_number(self.duration_seconds, "duration_seconds"),
        )
        object.__setattr__(
            self,
            "timestamp",
            require_optional_timezone_aware_datetime(self.timestamp, "timestamp"),
        )
