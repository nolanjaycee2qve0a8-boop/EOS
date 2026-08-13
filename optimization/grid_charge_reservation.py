"""Deterministic cheap-grid-charge allowance from existing PV headroom evidence.

This module consumes a completed PV headroom requirement rather than raw
forecast facts. It calculates planning allowance only; it creates no decision,
does not restrict PV charging, and does not replace physical revision.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import isfinite

from optimization.battery_planning import (
    BatteryOptimizationModel,
    BatteryOptimizationState,
)
from optimization.pv_headroom import PVHeadroomRequirement


def _require_positive_finite(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized) or normalized <= 0:
        raise ValueError(f"{field_name} must be finite and greater than 0")
    return normalized


def _require_non_negative_finite(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized) or normalized < 0:
        raise ValueError(f"{field_name} must be finite and greater than or equal to 0")
    return normalized


@dataclass(frozen=True, slots=True)
class HeadroomAwareGridChargeReservationInput:
    """Compose exact battery state/model, headroom evidence, and grid request."""

    battery_state: BatteryOptimizationState
    battery_model: BatteryOptimizationModel
    headroom_requirement: PVHeadroomRequirement
    requested_grid_charge_power_kw: float
    control_step_duration_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.battery_state, BatteryOptimizationState):
            raise TypeError("battery_state must be a BatteryOptimizationState")
        if not isinstance(self.battery_model, BatteryOptimizationModel):
            raise TypeError("battery_model must be a BatteryOptimizationModel")
        if not isinstance(self.headroom_requirement, PVHeadroomRequirement):
            raise TypeError("headroom_requirement must be a PVHeadroomRequirement")
        if (
            self.battery_model
            is not self.headroom_requirement.source_input.battery_model
        ):
            raise ValueError(
                "battery_model must preserve exact headroom requirement model identity"
            )
        object.__setattr__(
            self,
            "requested_grid_charge_power_kw",
            _require_positive_finite(
                self.requested_grid_charge_power_kw,
                "requested_grid_charge_power_kw",
            ),
        )
        object.__setattr__(
            self,
            "control_step_duration_seconds",
            _require_positive_finite(
                self.control_step_duration_seconds,
                "control_step_duration_seconds",
            ),
        )


@dataclass(frozen=True, slots=True)
class HeadroomAwareGridChargeReservation:
    """Read-only allowed cheap-grid-charge evidence for one current interval."""

    source_input: HeadroomAwareGridChargeReservationInput
    target_soc_fraction: float
    current_soc_fraction: float
    available_soc_charge_fraction: float
    available_stored_energy_kwh: float
    available_input_energy_kwh: float
    soc_limited_charge_power_kw: float
    requested_grid_charge_power_kw: float
    allowed_grid_charge_power_kw: float
    reservation_applied: bool

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, HeadroomAwareGridChargeReservationInput):
            raise TypeError(
                "source_input must be a HeadroomAwareGridChargeReservationInput"
            )
        for field_name in (
            "target_soc_fraction",
            "current_soc_fraction",
            "available_soc_charge_fraction",
            "available_stored_energy_kwh",
            "available_input_energy_kwh",
            "soc_limited_charge_power_kw",
            "requested_grid_charge_power_kw",
            "allowed_grid_charge_power_kw",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_non_negative_finite(getattr(self, field_name), field_name),
            )
        if not isinstance(self.reservation_applied, bool):
            raise TypeError("reservation_applied must be a bool")
        self._validate_formula()

    def _validate_formula(self) -> None:
        source = self.source_input
        model = source.battery_model
        expected_target = (
            source.headroom_requirement.recommended_pre_pv_max_soc_fraction
        )
        expected_current = source.battery_state.soc_fraction
        expected_soc_room = max(expected_target - expected_current, 0.0)
        expected_stored_energy = expected_soc_room * model.usable_capacity_kwh
        expected_input_energy = expected_stored_energy / model.charge_efficiency
        duration_hours = source.control_step_duration_seconds / 3600.0
        expected_soc_power = expected_input_energy / duration_hours
        expected_allowed = min(
            source.requested_grid_charge_power_kw,
            model.max_charge_power_kw,
            expected_soc_power,
        )
        expected = (
            expected_target,
            expected_current,
            expected_soc_room,
            expected_stored_energy,
            expected_input_energy,
            expected_soc_power,
            source.requested_grid_charge_power_kw,
            expected_allowed,
            expected_allowed < source.requested_grid_charge_power_kw,
        )
        actual = (
            self.target_soc_fraction,
            self.current_soc_fraction,
            self.available_soc_charge_fraction,
            self.available_stored_energy_kwh,
            self.available_input_energy_kwh,
            self.soc_limited_charge_power_kw,
            self.requested_grid_charge_power_kw,
            self.allowed_grid_charge_power_kw,
            self.reservation_applied,
        )
        if actual != expected:
            raise ValueError(
                "reservation values must match the exact allowance formula"
            )


class HeadroomAwareGridChargeReservationBoundary(ABC):
    """Define stateless calculation of cheap-grid-charge allowance evidence."""

    __slots__ = ()

    @abstractmethod
    def calculate(
        self,
        reservation_input: HeadroomAwareGridChargeReservationInput,
    ) -> HeadroomAwareGridChargeReservation:
        """Calculate an allowance only; never generate a battery action."""
        raise NotImplementedError


class DeterministicHeadroomAwareGridChargeReservationCalculator(
    HeadroomAwareGridChargeReservationBoundary
):
    """Calculate current cheap-grid allowance using supplied headroom evidence."""

    __slots__ = ()

    def calculate(
        self,
        reservation_input: HeadroomAwareGridChargeReservationInput,
    ) -> HeadroomAwareGridChargeReservation:
        if not isinstance(
            reservation_input,
            HeadroomAwareGridChargeReservationInput,
        ):
            raise TypeError(
                "reservation_input must be a HeadroomAwareGridChargeReservationInput"
            )
        source = reservation_input
        model = source.battery_model
        target = source.headroom_requirement.recommended_pre_pv_max_soc_fraction
        current = source.battery_state.soc_fraction
        soc_room = max(target - current, 0.0)
        stored_energy = soc_room * model.usable_capacity_kwh
        input_energy = stored_energy / model.charge_efficiency
        duration_hours = source.control_step_duration_seconds / 3600.0
        soc_power = input_energy / duration_hours
        allowed = min(
            source.requested_grid_charge_power_kw,
            model.max_charge_power_kw,
            soc_power,
        )
        return HeadroomAwareGridChargeReservation(
            source,
            target,
            current,
            soc_room,
            stored_energy,
            input_energy,
            soc_power,
            source.requested_grid_charge_power_kw,
            allowed,
            allowed < source.requested_grid_charge_power_kw,
        )
