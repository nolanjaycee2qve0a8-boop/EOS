"""Immutable time-of-use EMS capability."""

from dataclasses import dataclass
from math import isfinite

from capability.base import EMSCapabilityBoundary
from kernel.decision import DecisionContext, DecisionIntent


def _require_hours(value: object, field_name: str) -> tuple[int, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    for hour in value:
        if isinstance(hour, bool) or not isinstance(hour, int):
            raise TypeError(f"{field_name} must contain only int values")
        if not 0 <= hour <= 23:
            raise ValueError(f"{field_name} values must be between 0 and 23")
    if len(set(value)) != len(value):
        raise ValueError(f"{field_name} must not contain duplicate hours")
    return value


def _require_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    return normalized


def _require_non_negative_number(value: object, field_name: str) -> float:
    normalized = _require_number(value, field_name)
    if normalized < 0:
        raise ValueError(f"{field_name} must be greater than or equal to 0")
    return normalized


@dataclass(frozen=True, slots=True)
class TOUCapabilityParameters:
    """Caller-supplied immutable tariff, time, and intent facts.

    ``charge_hours`` and ``discharge_hours`` contain local clock hours from
    zero through 23, interpreted in the timezone carried by
    ``DecisionContext.timestamp``. The tuples must not overlap.

    Price thresholds are literal, unscaled CNY per kWh values.
    ``charge_power_intent_kw`` and ``discharge_power_intent_kw`` are
    non-negative literal kW magnitudes, not physical equipment limits.
    """

    charge_hours: tuple[int, ...]
    discharge_hours: tuple[int, ...]
    charge_price_ceiling_cny_per_kwh: float
    discharge_price_floor_cny_per_kwh: float
    charge_power_intent_kw: float
    discharge_power_intent_kw: float

    def __post_init__(self) -> None:
        charge_hours = _require_hours(self.charge_hours, "charge_hours")
        discharge_hours = _require_hours(self.discharge_hours, "discharge_hours")
        if not set(charge_hours).isdisjoint(discharge_hours):
            raise ValueError("charge_hours and discharge_hours must not overlap")

        object.__setattr__(
            self,
            "charge_price_ceiling_cny_per_kwh",
            _require_number(
                self.charge_price_ceiling_cny_per_kwh,
                "charge_price_ceiling_cny_per_kwh",
            ),
        )
        object.__setattr__(
            self,
            "discharge_price_floor_cny_per_kwh",
            _require_number(
                self.discharge_price_floor_cny_per_kwh,
                "discharge_price_floor_cny_per_kwh",
            ),
        )
        object.__setattr__(
            self,
            "charge_power_intent_kw",
            _require_non_negative_number(
                self.charge_power_intent_kw,
                "charge_power_intent_kw",
            ),
        )
        object.__setattr__(
            self,
            "discharge_power_intent_kw",
            _require_non_negative_number(
                self.discharge_power_intent_kw,
                "discharge_power_intent_kw",
            ),
        )


@dataclass(frozen=True, slots=True)
class TOUEnergyCapability(EMSCapabilityBoundary):
    """Generate a TOU intent from explicit immutable caller facts."""

    parameters: TOUCapabilityParameters

    def __post_init__(self) -> None:
        if not isinstance(self.parameters, TOUCapabilityParameters):
            raise TypeError("parameters must be a TOUCapabilityParameters")

    def evaluate(self, context: DecisionContext) -> DecisionIntent:
        """Return charge, discharge, or idle intent without enforcing limits."""
        if not isinstance(context, DecisionContext):
            raise TypeError("context must be a DecisionContext")

        hour = context.timestamp.hour
        price = context.electricity_price_cny_per_kwh

        if (
            hour in self.parameters.charge_hours
            and price <= self.parameters.charge_price_ceiling_cny_per_kwh
        ):
            power_intent_kw = self.parameters.charge_power_intent_kw
        elif (
            hour in self.parameters.discharge_hours
            and price >= self.parameters.discharge_price_floor_cny_per_kwh
        ):
            power_intent_kw = -self.parameters.discharge_power_intent_kw
        else:
            power_intent_kw = 0.0

        return DecisionIntent(battery_power_intent_kw=power_intent_kw)
