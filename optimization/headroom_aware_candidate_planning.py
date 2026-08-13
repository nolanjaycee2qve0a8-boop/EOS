"""Compose current cheap-grid reservation with net-load candidate planning.

This module intentionally adjusts at most the first planning step.  The
supplied battery state describes the beginning of the current horizon, not an
independent SOC for every future point.  Future SOC scheduling remains outside
this seam.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import isfinite

from decision_formation import DecisionIntent
from optimization.battery_planning import BatteryOptimizationInput
from optimization.grid_charge_reservation import (
    HeadroomAwareGridChargeReservation,
    HeadroomAwareGridChargeReservationBoundary,
    HeadroomAwareGridChargeReservationInput,
)
from optimization.model import OptimizationResult
from optimization.net_load_aware_baseline import NetLoadAwareBaselineOptimizer
from optimization.pv_headroom import PVHeadroomRequirement
from optimization.solution import OptimizationSolution, OptimizationSolutionStep
from optimization.solution_boundary import OptimizationSolveOutput


def _require_positive_seconds(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("control_step_duration_seconds must be a number")
    normalized = float(value)
    if not isfinite(normalized) or normalized <= 0:
        raise ValueError(
            "control_step_duration_seconds must be finite and greater than 0"
        )
    return normalized


@dataclass(frozen=True, slots=True)
class HeadroomAwareCandidatePlanningInput:
    """Retain exact battery facts and TASK-132 evidence for one horizon."""

    battery_input: BatteryOptimizationInput
    headroom_requirement: PVHeadroomRequirement
    control_step_duration_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.battery_input, BatteryOptimizationInput):
            raise TypeError("battery_input must be a BatteryOptimizationInput")
        if not isinstance(self.headroom_requirement, PVHeadroomRequirement):
            raise TypeError("headroom_requirement must be a PVHeadroomRequirement")
        if (
            self.headroom_requirement.source_input.battery_model
            is not self.battery_input.battery_model
        ):
            raise ValueError(
                "headroom requirement must preserve exact battery model identity"
            )
        object.__setattr__(
            self,
            "control_step_duration_seconds",
            _require_positive_seconds(self.control_step_duration_seconds),
        )


@dataclass(frozen=True, slots=True)
class HeadroomAwareCandidatePlanningResult:
    """Preserve candidate, optional current reservation, and final candidate."""

    source_input: HeadroomAwareCandidatePlanningInput
    source_candidate_output: OptimizationSolveOutput
    grid_charge_reservation: HeadroomAwareGridChargeReservation | None
    final_output: OptimizationSolveOutput

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, HeadroomAwareCandidatePlanningInput):
            raise TypeError(
                "source_input must be a HeadroomAwareCandidatePlanningInput"
            )
        if not isinstance(self.source_candidate_output, OptimizationSolveOutput):
            raise TypeError(
                "source_candidate_output must be an OptimizationSolveOutput"
            )
        if not isinstance(self.final_output, OptimizationSolveOutput):
            raise TypeError("final_output must be an OptimizationSolveOutput")
        if self.final_output is self.source_candidate_output:
            raise ValueError(
                "final_output must be distinct from source_candidate_output"
            )

        problem = self.source_input.battery_input.problem
        candidate = self.source_candidate_output
        final = self.final_output
        if candidate.result.source_problem is not problem:
            raise ValueError(
                "candidate output must preserve exact input problem identity"
            )
        if final.result.source_problem is not problem:
            raise ValueError("final output must preserve exact input problem identity")
        if candidate.result.outcome != final.result.outcome:
            raise ValueError("final output must preserve candidate outcome")
        if final.result is candidate.result:
            raise ValueError("final output must preserve a distinct result artifact")
        if final.solution.source_result is not final.result:
            raise ValueError("final solution must preserve exact final result identity")

        candidate_steps = candidate.solution.steps
        final_steps = final.solution.steps
        if candidate.result.outcome == "unavailable":
            if (
                candidate_steps
                or final_steps
                or self.grid_charge_reservation is not None
            ):
                raise ValueError(
                    "unavailable output must remain empty without reservation"
                )
            return
        if len(candidate_steps) != len(problem.forecast_horizon.points):
            raise ValueError("candidate must contain one step per forecast point")
        if len(final_steps) != len(candidate_steps):
            raise ValueError("final output must preserve candidate step coverage")
        for candidate_step, final_step in zip(
            candidate_steps, final_steps, strict=True
        ):
            if final_step.timestamp is not candidate_step.timestamp:
                raise ValueError("final steps must preserve exact timestamp identity")

        if not candidate_steps:
            if self.grid_charge_reservation is not None:
                raise ValueError("empty candidate output must not have a reservation")
            return

        first_candidate = candidate_steps[0]
        first_final = final_steps[0]
        if self.grid_charge_reservation is None:
            self._validate_unchanged(candidate_steps, final_steps)
            return

        reservation = self.grid_charge_reservation
        if not isinstance(reservation, HeadroomAwareGridChargeReservation):
            raise TypeError(
                "grid_charge_reservation must be a HeadroomAwareGridChargeReservation"
            )
        reservation_input = reservation.source_input
        if (
            reservation_input.battery_state
            is not self.source_input.battery_input.battery_state
        ):
            raise ValueError("reservation must preserve exact battery state identity")
        if (
            reservation_input.battery_model
            is not self.source_input.battery_input.battery_model
        ):
            raise ValueError("reservation must preserve exact battery model identity")
        if (
            reservation_input.headroom_requirement
            is not self.source_input.headroom_requirement
        ):
            raise ValueError("reservation must preserve exact headroom identity")
        if (
            reservation_input.control_step_duration_seconds
            != self.source_input.control_step_duration_seconds
        ):
            raise ValueError("reservation must preserve the exact duration")
        if (
            reservation.requested_grid_charge_power_kw
            != first_candidate.requested_power_kw
        ):
            raise ValueError("reservation must preserve current candidate grid request")
        allowed = reservation.allowed_grid_charge_power_kw
        expected_action = "charge" if allowed > 0 else "idle"
        if (
            first_final.intent.action != expected_action
            or first_final.requested_power_kw != allowed
        ):
            raise ValueError("final current step must preserve reservation allowance")
        self._validate_unchanged(candidate_steps[1:], final_steps[1:])

    @staticmethod
    def _validate_unchanged(
        candidate_steps: tuple[OptimizationSolutionStep, ...],
        final_steps: tuple[OptimizationSolutionStep, ...],
    ) -> None:
        for candidate_step, final_step in zip(
            candidate_steps, final_steps, strict=True
        ):
            if (
                final_step.intent is not candidate_step.intent
                or final_step.requested_power_kw != candidate_step.requested_power_kw
            ):
                raise ValueError("unreserved candidate steps must remain unchanged")


class HeadroomAwareCandidatePlanningBoundary(ABC):
    """Define a stateless current-step reservation planning seam."""

    __slots__ = ()

    @abstractmethod
    def plan(
        self,
        planning_input: HeadroomAwareCandidatePlanningInput,
    ) -> HeadroomAwareCandidatePlanningResult:
        """Return candidate evidence plus one explicit headroom-aware output."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class DeterministicHeadroomAwareCandidatePlanner(
    HeadroomAwareCandidatePlanningBoundary
):
    """Adjust only a current cheap-grid candidate using TASK-133 evidence."""

    candidate_optimizer: NetLoadAwareBaselineOptimizer
    grid_charge_reservation_calculator: HeadroomAwareGridChargeReservationBoundary

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_optimizer, NetLoadAwareBaselineOptimizer):
            raise TypeError(
                "candidate_optimizer must be a NetLoadAwareBaselineOptimizer"
            )
        if not isinstance(
            self.grid_charge_reservation_calculator,
            HeadroomAwareGridChargeReservationBoundary,
        ):
            raise TypeError(
                "grid_charge_reservation_calculator must be a "
                "HeadroomAwareGridChargeReservationBoundary"
            )

    def plan(
        self,
        planning_input: HeadroomAwareCandidatePlanningInput,
    ) -> HeadroomAwareCandidatePlanningResult:
        if not isinstance(planning_input, HeadroomAwareCandidatePlanningInput):
            raise TypeError(
                "planning_input must be a HeadroomAwareCandidatePlanningInput"
            )

        problem = planning_input.battery_input.problem
        candidate_output = self.candidate_optimizer.solve_with_solution(problem)
        self._validate_candidate_output(candidate_output, problem)
        candidate_steps = candidate_output.solution.steps
        reservation: HeadroomAwareGridChargeReservation | None = None

        if candidate_steps and self._is_current_cheap_grid_charge(
            planning_input,
            candidate_steps[0],
        ):
            reservation = self.grid_charge_reservation_calculator.calculate(
                HeadroomAwareGridChargeReservationInput(
                    planning_input.battery_input.battery_state,
                    planning_input.battery_input.battery_model,
                    planning_input.headroom_requirement,
                    candidate_steps[0].requested_power_kw,
                    planning_input.control_step_duration_seconds,
                )
            )

        final_result = OptimizationResult(problem, candidate_output.result.outcome)
        final_steps = self._final_steps(candidate_steps, reservation)
        final_output = OptimizationSolveOutput(
            final_result,
            OptimizationSolution(final_result, final_steps),
        )
        return HeadroomAwareCandidatePlanningResult(
            planning_input,
            candidate_output,
            reservation,
            final_output,
        )

    def _is_current_cheap_grid_charge(
        self,
        planning_input: HeadroomAwareCandidatePlanningInput,
        candidate_step: OptimizationSolutionStep,
    ) -> bool:
        """Use public TASK-130 facts; PV-surplus charging always remains exempt."""

        point = planning_input.battery_input.problem.forecast_horizon.points[0]
        configuration = self.candidate_optimizer.configuration
        return (
            point.pv_power_kw <= point.load_power_kw
            and point.electricity_price_cny_per_kwh is not None
            and point.electricity_price_cny_per_kwh
            <= configuration.low_price_threshold_cny_per_kwh
            and candidate_step.intent.action == "charge"
            and candidate_step.requested_power_kw
            == configuration.requested_grid_charge_power_kw
        )

    @staticmethod
    def _validate_candidate_output(
        candidate_output: OptimizationSolveOutput,
        problem: object,
    ) -> None:
        if not isinstance(candidate_output, OptimizationSolveOutput):
            raise TypeError(
                "candidate optimizer must return an OptimizationSolveOutput"
            )
        if candidate_output.result.source_problem is not problem:
            raise ValueError(
                "candidate output must preserve exact input problem identity"
            )
        if (
            candidate_output.result.outcome == "unavailable"
            and candidate_output.solution.steps
        ):
            raise ValueError("unavailable candidate output must be empty")

    @staticmethod
    def _final_steps(
        candidate_steps: tuple[OptimizationSolutionStep, ...],
        reservation: HeadroomAwareGridChargeReservation | None,
    ) -> tuple[OptimizationSolutionStep, ...]:
        if reservation is None:
            return tuple(
                OptimizationSolutionStep(
                    step.timestamp,
                    step.intent,
                    step.requested_power_kw,
                )
                for step in candidate_steps
            )
        allowed = reservation.allowed_grid_charge_power_kw
        first = candidate_steps[0]
        current_intent = first.intent if allowed > 0 else DecisionIntent("idle")
        current_step = OptimizationSolutionStep(
            first.timestamp,
            current_intent,
            allowed,
        )
        future_steps = tuple(
            OptimizationSolutionStep(
                step.timestamp, step.intent, step.requested_power_kw
            )
            for step in candidate_steps[1:]
        )
        return (current_step, *future_steps)
