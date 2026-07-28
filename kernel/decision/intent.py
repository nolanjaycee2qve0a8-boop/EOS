"""Immutable semantic intention produced by a decision policy."""

from dataclasses import dataclass

from kernel.decision.validation import require_number


@dataclass(frozen=True, slots=True)
class DecisionIntent:
    """Describe intended battery power before command generation.

    ``battery_power_intent_kw`` is a literal, unscaled value in kilowatts.
    Positive values mean charging the battery, negative values mean
    discharging the battery, and zero means idle. Any finite real value is
    valid; physical enforcement belongs to a later command-generation layer.
    """

    battery_power_intent_kw: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "battery_power_intent_kw",
            require_number(
                self.battery_power_intent_kw,
                "battery_power_intent_kw",
            ),
        )
