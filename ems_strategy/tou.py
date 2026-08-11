"""Concrete time-of-use strategy with caller-supplied immutable tariff facts."""

from dataclasses import dataclass
from math import isfinite
from typing import ClassVar

from decision_formation import DecisionIntent
from ems_strategy.boundary import EMSStrategyBoundary
from ems_strategy.context import EMSContext
from ems_strategy.decision import EMSDecision
from ems_strategy.descriptor import EMSStrategyDescriptor


def _require_finite_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    return normalized


def _require_positive_power(value: object, field_name: str) -> float:
    normalized = _require_finite_number(value, field_name)
    if normalized <= 0:
        raise ValueError(f"{field_name} must be greater than 0")
    return normalized


@dataclass(frozen=True, slots=True)
class TOUStrategyConfiguration:
    """Describe literal tariff thresholds and requested power magnitudes.

    Price thresholds are finite, signed, unscaled CNY per kWh values.
    Requested powers are finite positive raw kW magnitudes, not equipment
    limits. The configuration is caller supplied and has no service lookup.
    """

    low_price_threshold_cny_per_kwh: float
    high_price_threshold_cny_per_kwh: float
    charge_request_power_kw: float
    discharge_request_power_kw: float

    def __post_init__(self) -> None:
        low_price = _require_finite_number(
            self.low_price_threshold_cny_per_kwh,
            "low_price_threshold_cny_per_kwh",
        )
        high_price = _require_finite_number(
            self.high_price_threshold_cny_per_kwh,
            "high_price_threshold_cny_per_kwh",
        )
        if low_price >= high_price:
            raise ValueError(
                "low_price_threshold_cny_per_kwh must be less than "
                "high_price_threshold_cny_per_kwh"
            )
        object.__setattr__(self, "low_price_threshold_cny_per_kwh", low_price)
        object.__setattr__(self, "high_price_threshold_cny_per_kwh", high_price)
        object.__setattr__(
            self,
            "charge_request_power_kw",
            _require_positive_power(
                self.charge_request_power_kw,
                "charge_request_power_kw",
            ),
        )
        object.__setattr__(
            self,
            "discharge_request_power_kw",
            _require_positive_power(
                self.discharge_request_power_kw,
                "discharge_request_power_kw",
            ),
        )


@dataclass(frozen=True, slots=True)
class TOUStrategy(EMSStrategyBoundary):
    """Request a semantic Battery action from the current tariff fact only.

    Immutable configuration is declarative input, not retained runtime state.
    Physical feasibility and all execution remain downstream.
    """

    configuration: TOUStrategyConfiguration

    descriptor: ClassVar[EMSStrategyDescriptor] = EMSStrategyDescriptor(
        "time-of-use",
        "1.0",
    )

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, TOUStrategyConfiguration):
            raise TypeError("configuration must be a TOUStrategyConfiguration")

    def evaluate(self, context: EMSContext) -> EMSDecision:
        """Return one request preserving the exact supplied context identity."""
        if not isinstance(context, EMSContext):
            raise TypeError("context must be an EMSContext")

        price = context.source_context.electricity_price_cny_per_kwh
        if price <= self.configuration.low_price_threshold_cny_per_kwh:
            intent = DecisionIntent("charge")
            requested_power_kw = self.configuration.charge_request_power_kw
        elif price >= self.configuration.high_price_threshold_cny_per_kwh:
            intent = DecisionIntent("discharge")
            requested_power_kw = self.configuration.discharge_request_power_kw
        else:
            intent = DecisionIntent("idle")
            requested_power_kw = 0.0

        return EMSDecision(
            source_context=context,
            source_strategy=self.descriptor,
            intent=intent,
            requested_power_kw=requested_power_kw,
        )
