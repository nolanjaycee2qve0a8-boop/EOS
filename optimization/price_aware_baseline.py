"""Deterministic price-only baseline optimization implementation."""

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


@dataclass(frozen=True, slots=True)
class PriceAwareBaselineOptimizationConfiguration:
    """Declare explicit price thresholds and semantic request magnitude."""

    low_price_threshold_cny_per_kwh: float
    high_price_threshold_cny_per_kwh: float
    requested_power_kw: float

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
            "requested_power_kw",
            _require_positive_number(self.requested_power_kw, "requested_power_kw"),
        )
        if (
            self.low_price_threshold_cny_per_kwh
            >= self.high_price_threshold_cny_per_kwh
        ):
            raise ValueError(
                "low_price_threshold_cny_per_kwh must be less than "
                "high_price_threshold_cny_per_kwh"
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
class PriceAwareBaselineOptimizer(OptimizationSolutionBoundary):
    """Classify caller-provided price points into semantic planning values.

    This baseline supports exactly the ``energy_cost`` / ``minimize`` objective.
    It is not a mathematical solver and deliberately ignores non-price facts.
    """

    configuration: PriceAwareBaselineOptimizationConfiguration

    def __post_init__(self) -> None:
        if not isinstance(
            self.configuration,
            PriceAwareBaselineOptimizationConfiguration,
        ):
            raise TypeError(
                "configuration must be a PriceAwareBaselineOptimizationConfiguration"
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
                _intent_for_price(
                    point.electricity_price_cny_per_kwh, self.configuration
                ),
                _power_for_price(
                    point.electricity_price_cny_per_kwh, self.configuration
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


def _intent_for_price(
    price: float | None,
    configuration: PriceAwareBaselineOptimizationConfiguration,
) -> DecisionIntent:
    if price is not None and price <= configuration.low_price_threshold_cny_per_kwh:
        return DecisionIntent("charge")
    if price is not None and price >= configuration.high_price_threshold_cny_per_kwh:
        return DecisionIntent("discharge")
    return DecisionIntent("idle")


def _power_for_price(
    price: float | None,
    configuration: PriceAwareBaselineOptimizationConfiguration,
) -> float:
    if price is not None and (
        price <= configuration.low_price_threshold_cny_per_kwh
        or price >= configuration.high_price_threshold_cny_per_kwh
    ):
        return configuration.requested_power_kw
    return 0.0
