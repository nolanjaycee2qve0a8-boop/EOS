"""Pure deterministic import-cost evidence for future battery energy shifting.

This module answers a deliberately narrow planning question: for one kWh of
grid-side energy imported at a forecast point, is storing and later delivering
that energy against a more expensive future grid import gross-positive?

It does not decide charge quantity, inspect SOC, reserve headroom, create a
candidate, or execute an optimization, MPC, feasibility, actuation, or
simulation path.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from math import isclose, isfinite

from forecast import ForecastHorizon, ForecastPoint
from optimization.battery_planning import BatteryOptimizationModel

_MARGIN_ZERO_TOLERANCE = 1e-12


def _require_finite_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    return normalized


def _require_non_negative_index(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an int")
    if value < 0:
        raise ValueError(f"{field_name} must be greater than or equal to 0")
    return value


class EconomicShiftClassification(StrEnum):
    """Classify one marginal import-cost energy-shifting opportunity."""

    POSITIVE = "positive"
    BREAK_EVEN = "break_even"
    NEGATIVE = "negative"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class EconomicPlanningInput:
    """Compose exact forecast and battery-efficiency facts for marginal value.

    No duration is needed: all evidence is normalized to one kWh of grid-side
    charging input.  The input intentionally excludes SOC, headroom,
    reservation, candidate, simulator, and control facts.
    """

    forecast_horizon: ForecastHorizon
    battery_model: BatteryOptimizationModel

    def __post_init__(self) -> None:
        if not isinstance(self.forecast_horizon, ForecastHorizon):
            raise TypeError("forecast_horizon must be a ForecastHorizon")
        if not isinstance(self.battery_model, BatteryOptimizationModel):
            raise TypeError("battery_model must be a BatteryOptimizationModel")


@dataclass(frozen=True, slots=True)
class EconomicPlanningStepEvidence:
    """Retain exact one-step import-cost arbitrage evidence.

    ``gross_avoided_import_cost_per_grid_input_kwh`` equals the best future
    import price multiplied by charge and discharge efficiency.  The margin is
    that gross avoided cost minus the current import cost.  It is gross: no
    degradation, export revenue, or other cost is included.
    """

    source_index: int
    source_forecast_point: ForecastPoint
    import_price_cny_per_kwh: float | None
    best_future_import_price_cny_per_kwh: float | None
    best_future_source_index: int | None
    best_future_forecast_point: ForecastPoint | None
    round_trip_efficiency: float
    break_even_future_import_price_cny_per_kwh: float | None
    gross_avoided_import_cost_per_grid_input_kwh: float | None
    gross_shift_margin_per_grid_input_kwh: float | None
    classification: EconomicShiftClassification
    economically_positive_shift: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_index",
            _require_non_negative_index(self.source_index, "source_index"),
        )
        if not isinstance(self.source_forecast_point, ForecastPoint):
            raise TypeError("source_forecast_point must be a ForecastPoint")
        if not isinstance(self.classification, EconomicShiftClassification):
            raise TypeError("classification must be an EconomicShiftClassification")
        if not isinstance(self.economically_positive_shift, bool):
            raise TypeError("economically_positive_shift must be a bool")
        for field_name in (
            "import_price_cny_per_kwh",
            "best_future_import_price_cny_per_kwh",
            "break_even_future_import_price_cny_per_kwh",
            "gross_avoided_import_cost_per_grid_input_kwh",
            "gross_shift_margin_per_grid_input_kwh",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(
                    self,
                    field_name,
                    _require_finite_number(value, field_name),
                )
        object.__setattr__(
            self,
            "round_trip_efficiency",
            _require_finite_number(
                self.round_trip_efficiency,
                "round_trip_efficiency",
            ),
        )
        if not 0.0 < self.round_trip_efficiency <= 1.0:
            raise ValueError(
                "round_trip_efficiency must be greater than 0 and at most 1"
            )
        self._validate_future_pair()

    def _validate_future_pair(self) -> None:
        future_values = (
            self.best_future_import_price_cny_per_kwh,
            self.best_future_source_index,
            self.best_future_forecast_point,
        )
        if any(value is None for value in future_values) and not all(
            value is None for value in future_values
        ):
            raise ValueError(
                "future price, index, and point must be all present or absent"
            )
        if self.best_future_source_index is not None:
            object.__setattr__(
                self,
                "best_future_source_index",
                _require_non_negative_index(
                    self.best_future_source_index,
                    "best_future_source_index",
                ),
            )
        if self.best_future_forecast_point is not None and not isinstance(
            self.best_future_forecast_point,
            ForecastPoint,
        ):
            raise TypeError("best_future_forecast_point must be a ForecastPoint")


@dataclass(frozen=True, slots=True)
class EconomicPlanningEvidence:
    """Read-only ordered economic evidence retaining exact forecast provenance."""

    source_input: EconomicPlanningInput
    steps: tuple[EconomicPlanningStepEvidence, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, EconomicPlanningInput):
            raise TypeError("source_input must be an EconomicPlanningInput")
        if not isinstance(self.steps, tuple):
            raise TypeError("steps must be a tuple")
        points = self.source_input.forecast_horizon.points
        if len(self.steps) != len(points):
            raise ValueError("steps must contain one value per forecast point")
        for index, step in enumerate(self.steps):
            if not isinstance(step, EconomicPlanningStepEvidence):
                raise TypeError(
                    "steps must contain EconomicPlanningStepEvidence objects"
                )
            if (
                step.source_index != index
                or step.source_forecast_point is not points[index]
            ):
                raise ValueError(
                    "steps must preserve exact forecast point identity and caller order"
                )
            self._validate_step(step, points)

    def _validate_step(
        self,
        step: EconomicPlanningStepEvidence,
        points: tuple[ForecastPoint, ...],
    ) -> None:
        expected = _calculate_step(
            step.source_index, points, self.source_input.battery_model
        )
        actual = (
            step.import_price_cny_per_kwh,
            step.best_future_import_price_cny_per_kwh,
            step.best_future_source_index,
            step.best_future_forecast_point,
            step.round_trip_efficiency,
            step.break_even_future_import_price_cny_per_kwh,
            step.gross_avoided_import_cost_per_grid_input_kwh,
            step.gross_shift_margin_per_grid_input_kwh,
            step.classification,
            step.economically_positive_shift,
        )
        expected_values = (
            expected.import_price_cny_per_kwh,
            expected.best_future_import_price_cny_per_kwh,
            expected.best_future_source_index,
            expected.best_future_forecast_point,
            expected.round_trip_efficiency,
            expected.break_even_future_import_price_cny_per_kwh,
            expected.gross_avoided_import_cost_per_grid_input_kwh,
            expected.gross_shift_margin_per_grid_input_kwh,
            expected.classification,
            expected.economically_positive_shift,
        )
        if actual != expected_values:
            raise ValueError("step must match the exact deterministic economic formula")


class EconomicPlanningBoundary(ABC):
    """Define a stateless seam for pure import-cost planning evidence."""

    __slots__ = ()

    @abstractmethod
    def calculate(
        self, planning_input: EconomicPlanningInput
    ) -> EconomicPlanningEvidence:
        """Return evidence only; never decide, reserve, or execute charging."""
        raise NotImplementedError


class DeterministicEconomicPlanningCalculator(EconomicPlanningBoundary):
    """Calculate gross marginal grid-import shifting evidence exactly once."""

    __slots__ = ()

    def calculate(
        self, planning_input: EconomicPlanningInput
    ) -> EconomicPlanningEvidence:
        if not isinstance(planning_input, EconomicPlanningInput):
            raise TypeError("planning_input must be an EconomicPlanningInput")
        points = planning_input.forecast_horizon.points
        steps = tuple(
            _calculate_step(index, points, planning_input.battery_model)
            for index in range(len(points))
        )
        return EconomicPlanningEvidence(planning_input, steps)


def _calculate_step(
    source_index: int,
    points: tuple[ForecastPoint, ...],
    model: BatteryOptimizationModel,
) -> EconomicPlanningStepEvidence:
    point = points[source_index]
    round_trip_efficiency = model.charge_efficiency * model.discharge_efficiency
    current_price = point.electricity_price_cny_per_kwh

    # A missing current import price makes this source step unavailable.  When
    # the current price exists, missing-priced future points are skipped; no
    # zero-price fact is fabricated.
    if current_price is None:
        return _unavailable_step(source_index, point, round_trip_efficiency)

    future = _best_priced_future_point(source_index, points)
    if future is None:
        return _unavailable_step(
            source_index,
            point,
            round_trip_efficiency,
            current_price,
        )
    future_index, future_point = future
    future_price = future_point.electricity_price_cny_per_kwh
    if future_price is None:
        raise AssertionError("best priced future point must have an import price")
    gross_avoided_cost = future_price * round_trip_efficiency
    margin = gross_avoided_cost - current_price
    classification = _classify_margin(margin)
    return EconomicPlanningStepEvidence(
        source_index,
        point,
        current_price,
        future_price,
        future_index,
        future_point,
        round_trip_efficiency,
        current_price / round_trip_efficiency,
        gross_avoided_cost,
        margin,
        classification,
        classification is EconomicShiftClassification.POSITIVE,
    )


def _unavailable_step(
    source_index: int,
    point: ForecastPoint,
    round_trip_efficiency: float,
    current_price: float | None = None,
) -> EconomicPlanningStepEvidence:
    return EconomicPlanningStepEvidence(
        source_index,
        point,
        current_price,
        None,
        None,
        None,
        round_trip_efficiency,
        None if current_price is None else current_price / round_trip_efficiency,
        None,
        None,
        EconomicShiftClassification.UNAVAILABLE,
        False,
    )


def _best_priced_future_point(
    source_index: int,
    points: tuple[ForecastPoint, ...],
) -> tuple[int, ForecastPoint] | None:
    best: tuple[int, ForecastPoint] | None = None
    best_price: float | None = None
    for future_index in range(source_index + 1, len(points)):
        future_point = points[future_index]
        future_price = future_point.electricity_price_cny_per_kwh
        if future_price is None:
            continue
        if best_price is None or future_price > best_price:
            best = (future_index, future_point)
            best_price = future_price
    return best


def _classify_margin(margin: float) -> EconomicShiftClassification:
    if isclose(margin, 0.0, rel_tol=0.0, abs_tol=_MARGIN_ZERO_TOLERANCE):
        return EconomicShiftClassification.BREAK_EVEN
    if margin > 0.0:
        return EconomicShiftClassification.POSITIVE
    return EconomicShiftClassification.NEGATIVE
