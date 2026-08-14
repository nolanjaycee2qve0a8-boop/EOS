"""Compose one rolling PV opportunity with existing TASK-132 headroom evidence.

This module selects one exact caller-owned PV opportunity through TASK-140,
adapts its selected point references into a new ``ForecastHorizon``, and
delegates energy accounting unchanged to TASK-132.  It owns neither selection
semantics nor headroom mathematics.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import isfinite

from forecast import ForecastHorizon
from optimization.battery_planning import BatteryOptimizationModel
from optimization.pv_headroom import (
    PVHeadroomRequirement,
    PVHeadroomRequirementBoundary,
    PVHeadroomRequirementInput,
)
from optimization.pv_opportunity_window import (
    PVOpportunityWindow,
    PVOpportunityWindowConfiguration,
    PVOpportunityWindowSelectionBoundary,
    PVOpportunityWindowSelectionInput,
)


def _require_positive_finite_seconds(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("control_step_duration_seconds must be a number")
    normalized = float(value)
    if not isfinite(normalized) or normalized <= 0:
        raise ValueError(
            "control_step_duration_seconds must be finite and greater than 0"
        )
    return normalized


@dataclass(frozen=True, slots=True)
class RollingPVHeadroomRequirementInput:
    """Retain exact full forecast, battery model, duration, and window facts."""

    forecast_horizon: ForecastHorizon
    battery_model: BatteryOptimizationModel
    control_step_duration_seconds: float
    window_configuration: PVOpportunityWindowConfiguration

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
        if not isinstance(self.window_configuration, PVOpportunityWindowConfiguration):
            raise TypeError(
                "window_configuration must be a PVOpportunityWindowConfiguration"
            )


@dataclass(frozen=True, slots=True)
class RollingPVHeadroomRequirement:
    """Preserve exact selection, selected horizon, and TASK-132 evidence."""

    source_input: RollingPVHeadroomRequirementInput
    opportunity_window: PVOpportunityWindow
    selected_forecast_horizon: ForecastHorizon
    headroom_requirement: PVHeadroomRequirement

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, RollingPVHeadroomRequirementInput):
            raise TypeError("source_input must be a RollingPVHeadroomRequirementInput")
        if not isinstance(self.opportunity_window, PVOpportunityWindow):
            raise TypeError("opportunity_window must be a PVOpportunityWindow")
        if not isinstance(self.selected_forecast_horizon, ForecastHorizon):
            raise TypeError("selected_forecast_horizon must be a ForecastHorizon")
        if not isinstance(self.headroom_requirement, PVHeadroomRequirement):
            raise TypeError("headroom_requirement must be a PVHeadroomRequirement")
        self._validate_window_provenance()
        self._validate_selected_horizon()
        self._validate_headroom_provenance()

    def _validate_window_provenance(self) -> None:
        window_input = self.opportunity_window.source_input
        if window_input.forecast_horizon is not self.source_input.forecast_horizon:
            raise ValueError(
                "opportunity window must preserve exact source forecast identity"
            )
        if window_input.configuration is not self.source_input.window_configuration:
            raise ValueError(
                "opportunity window must preserve exact source configuration identity"
            )

    def _validate_selected_horizon(self) -> None:
        expected_points = tuple(
            step.forecast_point for step in self.opportunity_window.steps
        )
        actual_points = self.selected_forecast_horizon.points
        if len(actual_points) != len(expected_points):
            raise ValueError(
                "selected horizon must contain every selected window point"
            )
        for actual, expected in zip(actual_points, expected_points, strict=True):
            if actual is not expected:
                raise ValueError(
                    "selected horizon must preserve exact selected ForecastPoint "
                    "identity"
                )

    def _validate_headroom_provenance(self) -> None:
        requirement_input = self.headroom_requirement.source_input
        if requirement_input.forecast_horizon is not self.selected_forecast_horizon:
            raise ValueError(
                "headroom requirement must preserve exact selected horizon identity"
            )
        if requirement_input.battery_model is not self.source_input.battery_model:
            raise ValueError(
                "headroom requirement must preserve exact source battery model identity"
            )
        if (
            requirement_input.control_step_duration_seconds
            != self.source_input.control_step_duration_seconds
        ):
            raise ValueError("headroom requirement must preserve the exact duration")


class RollingPVHeadroomRequirementBoundary(ABC):
    """Define one stateless rolling-window-to-headroom composition seam."""

    __slots__ = ()

    @abstractmethod
    def calculate(
        self,
        requirement_input: RollingPVHeadroomRequirementInput,
    ) -> RollingPVHeadroomRequirement:
        """Select once and calculate existing TASK-132 evidence once."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class DeterministicRollingPVHeadroomRequirementCalculator(
    RollingPVHeadroomRequirementBoundary
):
    """Compose injected TASK-140 selection and TASK-132 accounting exactly once."""

    opportunity_window_selector: PVOpportunityWindowSelectionBoundary
    headroom_calculator: PVHeadroomRequirementBoundary

    def __post_init__(self) -> None:
        if not isinstance(
            self.opportunity_window_selector,
            PVOpportunityWindowSelectionBoundary,
        ):
            raise TypeError(
                "opportunity_window_selector must be a "
                "PVOpportunityWindowSelectionBoundary"
            )
        if not isinstance(self.headroom_calculator, PVHeadroomRequirementBoundary):
            raise TypeError(
                "headroom_calculator must be a PVHeadroomRequirementBoundary"
            )

    def calculate(
        self,
        requirement_input: RollingPVHeadroomRequirementInput,
    ) -> RollingPVHeadroomRequirement:
        if not isinstance(requirement_input, RollingPVHeadroomRequirementInput):
            raise TypeError(
                "requirement_input must be a RollingPVHeadroomRequirementInput"
            )
        window = self.opportunity_window_selector.select(
            PVOpportunityWindowSelectionInput(
                requirement_input.forecast_horizon,
                requirement_input.window_configuration,
            )
        )
        selected_horizon = ForecastHorizon(
            tuple(step.forecast_point for step in window.steps)
        )
        requirement = self.headroom_calculator.calculate(
            PVHeadroomRequirementInput(
                selected_horizon,
                requirement_input.battery_model,
                requirement_input.control_step_duration_seconds,
            )
        )
        return RollingPVHeadroomRequirement(
            requirement_input,
            window,
            selected_horizon,
            requirement,
        )
