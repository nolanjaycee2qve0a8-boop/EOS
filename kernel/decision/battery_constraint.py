"""Immutable battery constraint implementation for decision intentions."""

from dataclasses import dataclass

from kernel.decision.constraint import (
    DecisionConstraintBoundary,
    FeasibleDecisionIntent,
)
from kernel.decision.intent import DecisionIntent
from kernel.decision.validation import (
    require_non_negative_number,
    require_unit_interval,
)


@dataclass(frozen=True, slots=True)
class BatteryConstraintImplementation(DecisionConstraintBoundary):
    """Apply immutable battery facts to one semantic power intention.

    ``soc`` and ``reserve_soc`` are unitless fractions in the inclusive range
    from zero to one. ``max_charge_power_kw`` and
    ``max_discharge_power_kw`` are non-negative power magnitudes in raw kW.
    The instance owns only the immutable facts required for one evaluation
    context; it owns no history, cache, runtime, policy, or device state.
    """

    soc: float
    reserve_soc: float
    max_charge_power_kw: float
    max_discharge_power_kw: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "soc",
            require_unit_interval(self.soc, "soc"),
        )
        object.__setattr__(
            self,
            "reserve_soc",
            require_unit_interval(self.reserve_soc, "reserve_soc"),
        )
        object.__setattr__(
            self,
            "max_charge_power_kw",
            require_non_negative_number(
                self.max_charge_power_kw,
                "max_charge_power_kw",
            ),
        )
        object.__setattr__(
            self,
            "max_discharge_power_kw",
            require_non_negative_number(
                self.max_discharge_power_kw,
                "max_discharge_power_kw",
            ),
        )

    def evaluate(self, intent: DecisionIntent) -> FeasibleDecisionIntent:
        """Return an allowed intent without modifying the supplied intention."""
        if not isinstance(intent, DecisionIntent):
            raise TypeError("intent must be a DecisionIntent")

        requested_power_kw = intent.battery_power_intent_kw
        allowed_power_kw = requested_power_kw

        if requested_power_kw > 0:
            if self.soc >= 1:
                allowed_power_kw = 0.0
            else:
                allowed_power_kw = min(
                    requested_power_kw,
                    self.max_charge_power_kw,
                )
        elif requested_power_kw < 0:
            if self.soc <= self.reserve_soc:
                allowed_power_kw = 0.0
            else:
                allowed_power_kw = max(
                    requested_power_kw,
                    -self.max_discharge_power_kw,
                )

        if allowed_power_kw == requested_power_kw:
            allowed_intent = intent
        else:
            allowed_intent = DecisionIntent(
                battery_power_intent_kw=allowed_power_kw,
            )

        return FeasibleDecisionIntent(intent=allowed_intent)
