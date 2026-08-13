"""Deterministic price, PV, and load-aware baseline candidate optimization."""

from dataclasses import dataclass
from math import isfinite

from decision_formation import DecisionIntent
from optimization.model import (
    OptimizationObjective,
    OptimizationProblem,
    OptimizationResult,
)
from optimization.solution import OptimizationSolution, OptimizationSolutionStep
from optimization.solution_boundary import (
    OptimizationSolutionBoundary,
    OptimizationSolveOutput,
)


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
class NetLoadAwareBaselineOptimizationConfiguration:
    """Declare price thresholds and the distinct cheap-grid charge request."""

    low_price_threshold_cny_per_kwh: float
    high_price_threshold_cny_per_kwh: float
    requested_grid_charge_power_kw: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "low_price_threshold_cny_per_kwh",
            _require_finite_number(
                self.low_price_threshold_cny_per_kwh,
                "low_price_threshold_cny_per_kwh",
            ),
        )
        object.__setattr__(
            self,
            "high_price_threshold_cny_per_kwh",
            _require_finite_number(
                self.high_price_threshold_cny_per_kwh,
                "high_price_threshold_cny_per_kwh",
            ),
        )
        object.__setattr__(
            self,
            "requested_grid_charge_power_kw",
            _require_positive_number(
                self.requested_grid_charge_power_kw,
                "requested_grid_charge_power_kw",
            ),
        )
        if (
            self.low_price_threshold_cny_per_kwh
            >= self.high_price_threshold_cny_per_kwh
        ):
            raise ValueError(
                "low_price_threshold_cny_per_kwh must be less than "
                "high_price_threshold_cny_per_kwh"
            )


@dataclass(frozen=True, slots=True)
class NetLoadAwareBaselineOptimizer(OptimizationSolutionBoundary):
    """Create candidates using caller price and exact forecast net load facts.

    This is deliberately candidate-only logic. Battery SOC, battery limits, and
    all physical correction remain separate responsibilities of the existing
    physically-aware revision layer.
    """

    configuration: NetLoadAwareBaselineOptimizationConfiguration

    def __post_init__(self) -> None:
        if not isinstance(
            self.configuration,
            NetLoadAwareBaselineOptimizationConfiguration,
        ):
            raise TypeError(
                "configuration must be a NetLoadAwareBaselineOptimizationConfiguration"
            )

    def solve_with_solution(
        self,
        problem: OptimizationProblem,
    ) -> OptimizationSolveOutput:
        if not isinstance(problem, OptimizationProblem):
            raise TypeError("problem must be an OptimizationProblem")
        if not _has_supported_objective(problem):
            result = OptimizationResult(problem, "unavailable")
            return OptimizationSolveOutput(result, OptimizationSolution(result, ()))

        result = OptimizationResult(problem, "optimal")
        steps = tuple(
            OptimizationSolutionStep(
                point.timestamp,
                *_candidate_for_forecast_point(
                    point.pv_power_kw,
                    point.load_power_kw,
                    point.electricity_price_cny_per_kwh,
                    self.configuration,
                ),
            )
            for point in problem.forecast_horizon.points
        )
        return OptimizationSolveOutput(result, OptimizationSolution(result, steps))


def _has_supported_objective(problem: OptimizationProblem) -> bool:
    objectives = problem.objectives.objectives
    return len(objectives) == 1 and _is_supported_objective(objectives[0])


def _is_supported_objective(objective: OptimizationObjective) -> bool:
    return objective.name == "energy_cost" and objective.sense == "minimize"


def _candidate_for_forecast_point(
    pv_power_kw: float,
    load_power_kw: float,
    price: float | None,
    configuration: NetLoadAwareBaselineOptimizationConfiguration,
) -> tuple[DecisionIntent, float]:
    """Apply the explicit surplus, high-price, then low-price precedence."""

    pv_surplus_kw = max(pv_power_kw - load_power_kw, 0.0)
    load_deficit_kw = max(load_power_kw - pv_power_kw, 0.0)

    if pv_surplus_kw > 0:
        return DecisionIntent("charge"), pv_surplus_kw
    if (
        price is not None
        and price >= configuration.high_price_threshold_cny_per_kwh
        and load_deficit_kw > 0
    ):
        return DecisionIntent("discharge"), load_deficit_kw
    if price is not None and price <= configuration.low_price_threshold_cny_per_kwh:
        return DecisionIntent("charge"), configuration.requested_grid_charge_power_kw
    return DecisionIntent("idle"), 0.0
