"""Current cheap-grid-charge allowance from completed multi-opportunity evidence.

The schedule has already segmented forecast opportunities and calculated their
headroom targets.  This module reads only that immutable evidence plus the
current battery state and request; it never recomputes planning evidence or
decides whether charging should be requested.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import isfinite

from optimization.battery_planning import (
    BatteryOptimizationModel,
    BatteryOptimizationState,
)
from optimization.multi_opportunity_headroom_schedule import (
    MultiOpportunityHeadroomSchedule,
    MultiOpportunityHeadroomScheduleEntry,
)


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
        raise ValueError(f"{field_name} must be finite and non-negative")
    return normalized


@dataclass(frozen=True, slots=True)
class MultiOpportunityGridChargeReservationInput:
    """Compose exact schedule/model/state evidence with one current grid request."""

    headroom_schedule: MultiOpportunityHeadroomSchedule
    battery_state: BatteryOptimizationState
    battery_model: BatteryOptimizationModel
    requested_grid_charge_power_kw: float
    duration_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.headroom_schedule, MultiOpportunityHeadroomSchedule):
            raise TypeError(
                "headroom_schedule must be a MultiOpportunityHeadroomSchedule"
            )
        if not isinstance(self.battery_state, BatteryOptimizationState):
            raise TypeError("battery_state must be a BatteryOptimizationState")
        if not isinstance(self.battery_model, BatteryOptimizationModel):
            raise TypeError("battery_model must be a BatteryOptimizationModel")
        if self.headroom_schedule.source_input.battery_model is not self.battery_model:
            raise ValueError(
                "battery_model must preserve exact headroom schedule model identity"
            )
        object.__setattr__(
            self,
            "requested_grid_charge_power_kw",
            _require_non_negative_finite(
                self.requested_grid_charge_power_kw,
                "requested_grid_charge_power_kw",
            ),
        )
        object.__setattr__(
            self,
            "duration_seconds",
            _require_positive_finite(self.duration_seconds, "duration_seconds"),
        )


@dataclass(frozen=True, slots=True)
class MultiOpportunityGridChargeReservationResult:
    """Read-only allowance evidence from current SOC and a completed schedule.

    ``reservation_applied`` means final allowed power is strictly less than the
    caller's requested grid-charge power.  It can therefore be true when the
    model charge-power limit, current SOC room, or schedule target limits the
    request; it does not claim which limit caused the reduction.
    """

    source_input: MultiOpportunityGridChargeReservationInput
    selected_schedule_entry: MultiOpportunityHeadroomScheduleEntry | None
    target_soc_fraction: float
    current_soc_fraction: float
    available_soc_charge_fraction: float
    target_stored_energy_kwh: float
    available_stored_energy_room_kwh: float
    required_input_energy_kwh: float
    model_max_charge_power_kw: float
    soc_limited_charge_power_kw: float
    requested_grid_charge_power_kw: float
    allowed_grid_charge_power_kw: float
    reservation_applied: bool

    def __post_init__(self) -> None:
        if not isinstance(
            self.source_input, MultiOpportunityGridChargeReservationInput
        ):
            raise TypeError(
                "source_input must be a MultiOpportunityGridChargeReservationInput"
            )
        schedule_entries = self.source_input.headroom_schedule.entries
        expected_entry = schedule_entries[0] if schedule_entries else None
        if self.selected_schedule_entry is not expected_entry:
            raise ValueError("selected_schedule_entry must preserve exact first entry")
        for field_name in (
            "target_soc_fraction",
            "current_soc_fraction",
            "available_soc_charge_fraction",
            "target_stored_energy_kwh",
            "available_stored_energy_room_kwh",
            "required_input_energy_kwh",
            "model_max_charge_power_kw",
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
        selected = self.selected_schedule_entry
        expected_target = (
            selected.recommended_pre_opportunity_max_soc_fraction
            if selected is not None
            else model.max_soc_fraction
        )
        expected_current = source.battery_state.soc_fraction
        expected_soc_room = max(expected_target - expected_current, 0.0)
        expected_target_energy = expected_target * model.usable_capacity_kwh
        expected_stored_room = expected_soc_room * model.usable_capacity_kwh
        expected_input_energy = expected_stored_room / model.charge_efficiency
        duration_hours = source.duration_seconds / 3600.0
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
            expected_target_energy,
            expected_stored_room,
            expected_input_energy,
            model.max_charge_power_kw,
            expected_soc_power,
            source.requested_grid_charge_power_kw,
            expected_allowed,
            expected_allowed < source.requested_grid_charge_power_kw,
        )
        actual = (
            self.target_soc_fraction,
            self.current_soc_fraction,
            self.available_soc_charge_fraction,
            self.target_stored_energy_kwh,
            self.available_stored_energy_room_kwh,
            self.required_input_energy_kwh,
            self.model_max_charge_power_kw,
            self.soc_limited_charge_power_kw,
            self.requested_grid_charge_power_kw,
            self.allowed_grid_charge_power_kw,
            self.reservation_applied,
        )
        if actual != expected:
            raise ValueError(
                "reservation values must match the exact allowance formula"
            )


class MultiOpportunityGridChargeReservationBoundary(ABC):
    """Define stateless schedule-aware current cheap-grid allowance calculation."""

    __slots__ = ()

    @abstractmethod
    def calculate(
        self,
        reservation_input: MultiOpportunityGridChargeReservationInput,
    ) -> MultiOpportunityGridChargeReservationResult:
        """Calculate allowance only; never request, decide, or execute charging."""
        raise NotImplementedError


class DeterministicMultiOpportunityGridChargeReservationCalculator(
    MultiOpportunityGridChargeReservationBoundary
):
    """Use only the first schedule entry as the current next-opportunity target."""

    __slots__ = ()

    def calculate(
        self,
        reservation_input: MultiOpportunityGridChargeReservationInput,
    ) -> MultiOpportunityGridChargeReservationResult:
        if not isinstance(
            reservation_input,
            MultiOpportunityGridChargeReservationInput,
        ):
            raise TypeError(
                "reservation_input must be a MultiOpportunityGridChargeReservationInput"
            )
        source = reservation_input
        model = source.battery_model
        selected = (
            source.headroom_schedule.entries[0]
            if source.headroom_schedule.entries
            else None
        )
        target = (
            selected.recommended_pre_opportunity_max_soc_fraction
            if selected is not None
            else model.max_soc_fraction
        )
        current = source.battery_state.soc_fraction
        soc_room = max(target - current, 0.0)
        target_energy = target * model.usable_capacity_kwh
        stored_room = soc_room * model.usable_capacity_kwh
        input_energy = stored_room / model.charge_efficiency
        duration_hours = source.duration_seconds / 3600.0
        soc_power = input_energy / duration_hours
        allowed = min(
            source.requested_grid_charge_power_kw,
            model.max_charge_power_kw,
            soc_power,
        )
        return MultiOpportunityGridChargeReservationResult(
            source,
            selected,
            target,
            current,
            soc_room,
            target_energy,
            stored_room,
            input_energy,
            model.max_charge_power_kw,
            soc_power,
            source.requested_grid_charge_power_kw,
            allowed,
            allowed < source.requested_grid_charge_power_kw,
        )
