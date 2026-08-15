"""Pure battery-throughput degradation-cost evidence.

This module multiplies caller-supplied aggregated battery throughput by one
caller-supplied cost rate. It does not inspect battery state, power traces,
aging conditions, planning, control, or simulation artifacts.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import isfinite


def _require_non_negative_finite(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized) or normalized < 0.0:
        raise ValueError(f"{field_name} must be finite and non-negative")
    return normalized


@dataclass(frozen=True, slots=True)
class BatteryDegradationCostInput:
    """Caller-owned throughput basis and externally assigned degradation rate.

    Throughput is a non-negative scalar whose accounting basis is caller-owned:
    it may be charge-only, discharge-only, combined, AC-side, DC-side, or any
    other explicitly consistent definition. This contract does not decide it.
    """

    battery_throughput_kwh: float
    degradation_cost_per_throughput_kwh: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "battery_throughput_kwh",
            _require_non_negative_finite(
                self.battery_throughput_kwh,
                "battery_throughput_kwh",
            ),
        )
        object.__setattr__(
            self,
            "degradation_cost_per_throughput_kwh",
            _require_non_negative_finite(
                self.degradation_cost_per_throughput_kwh,
                "degradation_cost_per_throughput_kwh",
            ),
        )


@dataclass(frozen=True, slots=True)
class BatteryDegradationCostEvidence:
    """Degradation-cost evidence from caller-supplied throughput terms only."""

    source_input: BatteryDegradationCostInput
    battery_throughput_kwh: float
    degradation_cost_per_throughput_kwh: float
    battery_degradation_cost: float

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, BatteryDegradationCostInput):
            raise TypeError("source_input must be a BatteryDegradationCostInput")
        for field_name in (
            "battery_throughput_kwh",
            "degradation_cost_per_throughput_kwh",
            "battery_degradation_cost",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_non_negative_finite(getattr(self, field_name), field_name),
            )
        if (
            self.battery_throughput_kwh != self.source_input.battery_throughput_kwh
            or self.degradation_cost_per_throughput_kwh
            != self.source_input.degradation_cost_per_throughput_kwh
        ):
            raise ValueError("degradation terms must preserve exact input semantics")
        if (
            self.battery_degradation_cost
            != self.battery_throughput_kwh * self.degradation_cost_per_throughput_kwh
        ):
            raise ValueError(
                "battery_degradation_cost must equal throughput times cost rate"
            )


class BatteryDegradationCostBoundary(ABC):
    """Define a stateless battery-degradation-cost evidence seam."""

    __slots__ = ()

    @abstractmethod
    def calculate(
        self,
        degradation_input: BatteryDegradationCostInput,
    ) -> BatteryDegradationCostEvidence:
        """Multiply supplied throughput and rate only."""
        raise NotImplementedError


class DeterministicBatteryDegradationCostCalculator(BatteryDegradationCostBoundary):
    """Apply the frozen battery-throughput times cost-rate formula."""

    __slots__ = ()

    def calculate(
        self,
        degradation_input: BatteryDegradationCostInput,
    ) -> BatteryDegradationCostEvidence:
        if not isinstance(degradation_input, BatteryDegradationCostInput):
            raise TypeError("degradation_input must be a BatteryDegradationCostInput")
        return BatteryDegradationCostEvidence(
            degradation_input,
            degradation_input.battery_throughput_kwh,
            degradation_input.degradation_cost_per_throughput_kwh,
            degradation_input.battery_throughput_kwh
            * degradation_input.degradation_cost_per_throughput_kwh,
        )
