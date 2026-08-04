"""Immutable semantic intent contract for Phase 5 decision formation."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class DecisionIntent:
    """Describe one semantic EMS action without execution meaning.

    ``action`` is exactly ``"charge"``, ``"discharge"``, or ``"idle"``.
    The action does not define a device power sign, power magnitude, command,
    protocol operation, execution state, physical constraint, or optimization
    result. Converting an intent into a command belongs to a separate future
    boundary.
    """

    action: Literal["charge", "discharge", "idle"]

    def __post_init__(self) -> None:
        if not isinstance(self.action, str):
            raise TypeError("action must be a str")
        if self.action not in ("charge", "discharge", "idle"):
            raise ValueError("action must be 'charge', 'discharge', or 'idle'")
