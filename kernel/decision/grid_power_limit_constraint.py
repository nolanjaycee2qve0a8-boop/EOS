"""Immutable grid import and export power limit constraint."""

from dataclasses import dataclass

from kernel.decision.constraint import FeasibleDecisionIntent
from kernel.decision.grid_constraint import GridConstraintBoundary
from kernel.decision.intent import DecisionIntent
from kernel.decision.validation import (
    require_non_negative_number,
    require_number,
)


@dataclass(frozen=True, slots=True)
class GridPowerLimitConstraintImplementation(GridConstraintBoundary):
    """Limit projected grid exchange using immutable grid-side facts.

    All fields are literal, unscaled kW values. ``grid_power_baseline_kw`` is
    the grid power before applying the supplied battery intent: positive means
    grid import, negative means grid export, and zero means balanced exchange.
    ``max_import_power_kw`` and ``max_export_power_kw`` are non-negative power
    magnitudes.
    """

    grid_power_baseline_kw: float
    max_import_power_kw: float
    max_export_power_kw: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "grid_power_baseline_kw",
            require_number(
                self.grid_power_baseline_kw,
                "grid_power_baseline_kw",
            ),
        )
        object.__setattr__(
            self,
            "max_import_power_kw",
            require_non_negative_number(
                self.max_import_power_kw,
                "max_import_power_kw",
            ),
        )
        object.__setattr__(
            self,
            "max_export_power_kw",
            require_non_negative_number(
                self.max_export_power_kw,
                "max_export_power_kw",
            ),
        )

    def evaluate(self, intent: DecisionIntent) -> FeasibleDecisionIntent:
        """Clamp projected grid exchange without mutating the supplied intent."""
        if not isinstance(intent, DecisionIntent):
            raise TypeError("intent must be a DecisionIntent")

        requested_intent_kw = intent.battery_power_intent_kw
        projected_grid_power_kw = self.grid_power_baseline_kw + requested_intent_kw
        if (
            -self.max_export_power_kw
            <= projected_grid_power_kw
            <= self.max_import_power_kw
        ):
            return FeasibleDecisionIntent(intent=intent)

        allowed_grid_power_kw = min(
            max(
                projected_grid_power_kw,
                -self.max_export_power_kw,
            ),
            self.max_import_power_kw,
        )
        allowed_intent_kw = allowed_grid_power_kw - self.grid_power_baseline_kw
        return FeasibleDecisionIntent(
            intent=DecisionIntent(
                battery_power_intent_kw=allowed_intent_kw,
            )
        )
