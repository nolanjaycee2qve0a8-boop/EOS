"""Concrete peak-shaving strategy with immutable demand-limit configuration."""

from dataclasses import dataclass
from math import isfinite
from typing import ClassVar

from decision_formation import DecisionIntent
from ems_strategy.boundary import EMSStrategyBoundary
from ems_strategy.context import EMSContext
from ems_strategy.decision import EMSDecision
from ems_strategy.descriptor import EMSStrategyDescriptor


@dataclass(frozen=True, slots=True)
class PeakShavingConfiguration:
    """Describe one caller-supplied finite non-negative Load limit in raw kW."""

    demand_limit_kw: float

    def __post_init__(self) -> None:
        value = self.demand_limit_kw
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise TypeError("demand_limit_kw must be a number")
        normalized = float(value)
        if not isfinite(normalized) or normalized < 0:
            raise ValueError("demand_limit_kw must be finite and non-negative")
        object.__setattr__(self, "demand_limit_kw", normalized)


@dataclass(frozen=True, slots=True)
class PeakShavingStrategy(EMSStrategyBoundary):
    """Request discharge only when current Load exceeds the configured limit.

    Immutable configuration is declarative input, not retained runtime state.
    Battery feasibility and all execution remain downstream.
    """

    configuration: PeakShavingConfiguration

    descriptor: ClassVar[EMSStrategyDescriptor] = EMSStrategyDescriptor(
        "peak-shaving",
        "1.0",
    )

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, PeakShavingConfiguration):
            raise TypeError("configuration must be a PeakShavingConfiguration")

    def evaluate(self, context: EMSContext) -> EMSDecision:
        """Return one request preserving the exact supplied context identity."""
        if not isinstance(context, EMSContext):
            raise TypeError("context must be an EMSContext")

        load_power_kw = context.source_context.load_power_kw
        if load_power_kw > self.configuration.demand_limit_kw:
            intent = DecisionIntent("discharge")
            requested_power_kw = load_power_kw - self.configuration.demand_limit_kw
        else:
            intent = DecisionIntent("idle")
            requested_power_kw = 0.0

        return EMSDecision(
            source_context=context,
            source_strategy=self.descriptor,
            intent=intent,
            requested_power_kw=requested_power_kw,
        )
