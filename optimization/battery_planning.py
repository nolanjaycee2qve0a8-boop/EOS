"""Immutable battery planning facts for future physically-aware optimization."""

from dataclasses import dataclass
from math import isfinite

from optimization.model import OptimizationProblem


def _require_finite_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    return normalized


def _require_positive_number(value: object, field_name: str) -> float:
    normalized = _require_finite_number(value, field_name)
    if normalized <= 0:
        raise ValueError(f"{field_name} must be greater than 0")
    return normalized


@dataclass(frozen=True, slots=True)
class BatteryOptimizationState:
    """Describe the current normalized SOC at the start of one horizon."""

    soc_fraction: float

    def __post_init__(self) -> None:
        soc_fraction = _require_finite_number(self.soc_fraction, "soc_fraction")
        if not 0.0 <= soc_fraction <= 1.0:
            raise ValueError("soc_fraction must be between 0 and 1")
        object.__setattr__(self, "soc_fraction", soc_fraction)


@dataclass(frozen=True, slots=True)
class BatteryOptimizationModel:
    """Declare immutable planning limits without evaluating a future horizon."""

    usable_capacity_kwh: float
    min_soc_fraction: float
    max_soc_fraction: float
    max_charge_power_kw: float
    max_discharge_power_kw: float
    charge_efficiency: float
    discharge_efficiency: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "usable_capacity_kwh",
            _require_positive_number(self.usable_capacity_kwh, "usable_capacity_kwh"),
        )
        object.__setattr__(
            self,
            "min_soc_fraction",
            _require_finite_number(self.min_soc_fraction, "min_soc_fraction"),
        )
        object.__setattr__(
            self,
            "max_soc_fraction",
            _require_finite_number(self.max_soc_fraction, "max_soc_fraction"),
        )
        if not 0.0 <= self.min_soc_fraction < self.max_soc_fraction <= 1.0:
            raise ValueError(
                "min_soc_fraction and max_soc_fraction must satisfy 0 <= min < max <= 1"
            )
        object.__setattr__(
            self,
            "max_charge_power_kw",
            _require_positive_number(
                self.max_charge_power_kw,
                "max_charge_power_kw",
            ),
        )
        object.__setattr__(
            self,
            "max_discharge_power_kw",
            _require_positive_number(
                self.max_discharge_power_kw,
                "max_discharge_power_kw",
            ),
        )
        object.__setattr__(
            self,
            "charge_efficiency",
            _require_positive_number(self.charge_efficiency, "charge_efficiency"),
        )
        object.__setattr__(
            self,
            "discharge_efficiency",
            _require_positive_number(
                self.discharge_efficiency,
                "discharge_efficiency",
            ),
        )
        if self.charge_efficiency > 1.0:
            raise ValueError("charge_efficiency must be less than or equal to 1")
        if self.discharge_efficiency > 1.0:
            raise ValueError("discharge_efficiency must be less than or equal to 1")


@dataclass(frozen=True, slots=True)
class BatteryOptimizationInput:
    """Compose exact caller-owned optimization and battery planning facts."""

    problem: OptimizationProblem
    battery_state: BatteryOptimizationState
    battery_model: BatteryOptimizationModel

    def __post_init__(self) -> None:
        if not isinstance(self.problem, OptimizationProblem):
            raise TypeError("problem must be an OptimizationProblem")
        if not isinstance(self.battery_state, BatteryOptimizationState):
            raise TypeError("battery_state must be a BatteryOptimizationState")
        if not isinstance(self.battery_model, BatteryOptimizationModel):
            raise TypeError("battery_model must be a BatteryOptimizationModel")
