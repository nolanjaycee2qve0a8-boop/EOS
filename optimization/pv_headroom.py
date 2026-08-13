"""Deterministic future-PV battery-headroom planning evidence.

This module estimates the storage room that would be desirable before a
caller-supplied future PV opportunity.  It deliberately does not inspect
current SOC, electricity price, decisions, physical revision, or execution.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import isfinite

from forecast import ForecastHorizon, ForecastPoint
from optimization.battery_planning import BatteryOptimizationModel


def _require_positive_finite_seconds(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("control_step_duration_seconds must be a number")
    normalized = float(value)
    if not isfinite(normalized) or normalized <= 0:
        raise ValueError(
            "control_step_duration_seconds must be finite and greater than 0"
        )
    return normalized


def _require_non_negative_finite(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized) or normalized < 0:
        raise ValueError(f"{field_name} must be finite and greater than or equal to 0")
    return normalized


def _require_finite_calculation(value: float, field_name: str) -> float:
    if not isfinite(value):
        raise ValueError(f"{field_name} calculation must be finite")
    return value


@dataclass(frozen=True, slots=True)
class PVHeadroomRequirementInput:
    """Compose exact caller-owned forecast, battery capability, and step size."""

    forecast_horizon: ForecastHorizon
    battery_model: BatteryOptimizationModel
    control_step_duration_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.forecast_horizon, ForecastHorizon):
            raise TypeError("forecast_horizon must be a ForecastHorizon")
        if not isinstance(self.battery_model, BatteryOptimizationModel):
            raise TypeError("battery_model must be a BatteryOptimizationModel")
        object.__setattr__(
            self,
            "control_step_duration_seconds",
            _require_positive_finite_seconds(self.control_step_duration_seconds),
        )


@dataclass(frozen=True, slots=True)
class PVHeadroomForecastStep:
    """Retain one exact forecast point and its PV absorption estimate."""

    forecast_point: ForecastPoint
    pv_surplus_power_kw: float
    absorbable_charge_power_kw: float
    absorbable_input_energy_kwh: float
    stored_energy_delta_kwh: float

    def __post_init__(self) -> None:
        if not isinstance(self.forecast_point, ForecastPoint):
            raise TypeError("forecast_point must be a ForecastPoint")
        for field_name in (
            "pv_surplus_power_kw",
            "absorbable_charge_power_kw",
            "absorbable_input_energy_kwh",
            "stored_energy_delta_kwh",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_non_negative_finite(getattr(self, field_name), field_name),
            )
        if self.absorbable_charge_power_kw > self.pv_surplus_power_kw:
            raise ValueError(
                "absorbable_charge_power_kw must not exceed pv_surplus_power_kw"
            )


@dataclass(frozen=True, slots=True)
class PVHeadroomRequirement:
    """Read-only headroom evidence derived from one exact planning input."""

    source_input: PVHeadroomRequirementInput
    steps: tuple[PVHeadroomForecastStep, ...]
    total_forecast_pv_surplus_energy_kwh: float
    total_absorbable_pv_input_energy_kwh: float
    required_headroom_energy_kwh: float
    required_headroom_soc_fraction: float
    recommended_pre_pv_max_soc_fraction: float

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, PVHeadroomRequirementInput):
            raise TypeError("source_input must be a PVHeadroomRequirementInput")
        if not isinstance(self.steps, tuple):
            raise TypeError("steps must be a tuple")
        points = self.source_input.forecast_horizon.points
        if len(self.steps) != len(points):
            raise ValueError("steps must contain one value per forecast point")
        for index, step in enumerate(self.steps):
            if not isinstance(step, PVHeadroomForecastStep):
                raise TypeError("steps must contain PVHeadroomForecastStep objects")
            if step.forecast_point is not points[index]:
                raise ValueError(
                    "steps must preserve exact forecast point identity and caller order"
                )
            self._validate_step(step)
        for field_name in (
            "total_forecast_pv_surplus_energy_kwh",
            "total_absorbable_pv_input_energy_kwh",
            "required_headroom_energy_kwh",
            "required_headroom_soc_fraction",
            "recommended_pre_pv_max_soc_fraction",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_non_negative_finite(getattr(self, field_name), field_name),
            )
        self._validate_totals()

    def _validate_step(self, step: PVHeadroomForecastStep) -> None:
        source_input = self.source_input
        point = step.forecast_point
        duration_hours = source_input.control_step_duration_seconds / 3600.0
        expected_surplus = max(point.pv_power_kw - point.load_power_kw, 0.0)
        expected_power = min(
            expected_surplus,
            source_input.battery_model.max_charge_power_kw,
        )
        expected_input_energy = _require_finite_calculation(
            expected_power * duration_hours,
            "absorbable_input_energy_kwh",
        )
        expected_stored_energy = _require_finite_calculation(
            expected_input_energy * source_input.battery_model.charge_efficiency,
            "stored_energy_delta_kwh",
        )
        if step.pv_surplus_power_kw != expected_surplus:
            raise ValueError("step must preserve the exact forecast PV surplus")
        if step.absorbable_charge_power_kw != expected_power:
            raise ValueError("step must preserve the exact absorbable charge power")
        if step.absorbable_input_energy_kwh != expected_input_energy:
            raise ValueError("step must preserve the exact absorbable input energy")
        if step.stored_energy_delta_kwh != expected_stored_energy:
            raise ValueError("step must preserve the exact stored energy delta")

    def _validate_totals(self) -> None:
        source_input = self.source_input
        model = source_input.battery_model
        duration_hours = source_input.control_step_duration_seconds / 3600.0
        expected_surplus_total = _require_finite_calculation(
            sum(step.pv_surplus_power_kw * duration_hours for step in self.steps),
            "total_forecast_pv_surplus_energy_kwh",
        )
        expected_absorbable_total = _require_finite_calculation(
            sum(step.absorbable_input_energy_kwh for step in self.steps),
            "total_absorbable_pv_input_energy_kwh",
        )
        raw_headroom = _require_finite_calculation(
            sum(step.stored_energy_delta_kwh for step in self.steps),
            "required_headroom_energy_kwh",
        )
        usable_window = model.usable_capacity_kwh * (
            model.max_soc_fraction - model.min_soc_fraction
        )
        expected_headroom = min(raw_headroom, usable_window)
        expected_headroom_soc = expected_headroom / model.usable_capacity_kwh
        expected_recommended_max = max(
            model.min_soc_fraction,
            model.max_soc_fraction - expected_headroom_soc,
        )
        expected = (
            expected_surplus_total,
            expected_absorbable_total,
            expected_headroom,
            expected_headroom_soc,
            expected_recommended_max,
        )
        actual = (
            self.total_forecast_pv_surplus_energy_kwh,
            self.total_absorbable_pv_input_energy_kwh,
            self.required_headroom_energy_kwh,
            self.required_headroom_soc_fraction,
            self.recommended_pre_pv_max_soc_fraction,
        )
        if actual != expected:
            raise ValueError("requirement totals must match the exact planning formula")


class PVHeadroomRequirementBoundary(ABC):
    """Define stateless deterministic future-PV headroom estimation."""

    __slots__ = ()

    @abstractmethod
    def calculate(
        self,
        requirement_input: PVHeadroomRequirementInput,
    ) -> PVHeadroomRequirement:
        """Produce planning evidence only; never decide or execute charging."""
        raise NotImplementedError


class DeterministicPVHeadroomRequirementCalculator(PVHeadroomRequirementBoundary):
    """Calculate ordered future-PV headroom evidence from supplied facts only."""

    __slots__ = ()

    def calculate(
        self,
        requirement_input: PVHeadroomRequirementInput,
    ) -> PVHeadroomRequirement:
        if not isinstance(requirement_input, PVHeadroomRequirementInput):
            raise TypeError("requirement_input must be a PVHeadroomRequirementInput")
        model = requirement_input.battery_model
        duration_hours = requirement_input.control_step_duration_seconds / 3600.0
        steps = tuple(
            self._step(point, model, duration_hours)
            for point in requirement_input.forecast_horizon.points
        )
        total_surplus = _require_finite_calculation(
            sum(step.pv_surplus_power_kw * duration_hours for step in steps),
            "total_forecast_pv_surplus_energy_kwh",
        )
        total_absorbable = _require_finite_calculation(
            sum(step.absorbable_input_energy_kwh for step in steps),
            "total_absorbable_pv_input_energy_kwh",
        )
        raw_headroom = _require_finite_calculation(
            sum(step.stored_energy_delta_kwh for step in steps),
            "required_headroom_energy_kwh",
        )
        usable_window = model.usable_capacity_kwh * (
            model.max_soc_fraction - model.min_soc_fraction
        )
        required_headroom = min(raw_headroom, usable_window)
        required_headroom_soc = required_headroom / model.usable_capacity_kwh
        recommended_max_soc = max(
            model.min_soc_fraction,
            model.max_soc_fraction - required_headroom_soc,
        )
        return PVHeadroomRequirement(
            requirement_input,
            steps,
            total_surplus,
            total_absorbable,
            required_headroom,
            required_headroom_soc,
            recommended_max_soc,
        )

    @staticmethod
    def _step(
        point: ForecastPoint,
        model: BatteryOptimizationModel,
        duration_hours: float,
    ) -> PVHeadroomForecastStep:
        pv_surplus = max(point.pv_power_kw - point.load_power_kw, 0.0)
        absorbable_power = min(pv_surplus, model.max_charge_power_kw)
        absorbable_energy = _require_finite_calculation(
            absorbable_power * duration_hours,
            "absorbable_input_energy_kwh",
        )
        stored_energy = _require_finite_calculation(
            absorbable_energy * model.charge_efficiency,
            "stored_energy_delta_kwh",
        )
        return PVHeadroomForecastStep(
            point,
            pv_surplus,
            absorbable_power,
            absorbable_energy,
            stored_energy,
        )
