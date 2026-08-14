"""Compose schedule-aware reservation with one net-load candidate horizon.

This parallel TASK-149 seam consumes completed TASK-147 schedule evidence.  It
never derives PV opportunities, computes headroom, or performs physical
revision.  Only the current candidate step can be changed; future steps remain
the exact objects supplied by the source candidate output.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import isfinite

from decision_formation import DecisionIntent
from optimization.battery_planning import (
    BatteryOptimizationModel,
    BatteryOptimizationState,
)
from optimization.model import OptimizationProblem, OptimizationResult
from optimization.multi_opportunity_grid_charge_reservation import (
    MultiOpportunityGridChargeReservationBoundary,
    MultiOpportunityGridChargeReservationInput,
    MultiOpportunityGridChargeReservationResult,
)
from optimization.multi_opportunity_headroom_schedule import (
    MultiOpportunityHeadroomSchedule,
)
from optimization.net_load_aware_baseline import (
    NetLoadAwareBaselineOptimizationConfiguration,
    NetLoadAwareBaselineOptimizer,
)
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
class MultiOpportunityCandidatePlanningInput:
    """Retain exact current facts and completed multi-opportunity evidence.

    ``control_step_duration_seconds`` is explicit caller-owned planning data for
    TASK-148's power conversion.  It is not generated from a clock or inferred
    from future timestamps.
    """

    problem: OptimizationProblem
    configuration: NetLoadAwareBaselineOptimizationConfiguration
    battery_state: BatteryOptimizationState
    battery_model: BatteryOptimizationModel
    headroom_schedule: MultiOpportunityHeadroomSchedule
    control_step_duration_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.problem, OptimizationProblem):
            raise TypeError("problem must be an OptimizationProblem")
        if not isinstance(
            self.configuration,
            NetLoadAwareBaselineOptimizationConfiguration,
        ):
            raise TypeError(
                "configuration must be a NetLoadAwareBaselineOptimizationConfiguration"
            )
        if not isinstance(self.battery_state, BatteryOptimizationState):
            raise TypeError("battery_state must be a BatteryOptimizationState")
        if not isinstance(self.battery_model, BatteryOptimizationModel):
            raise TypeError("battery_model must be a BatteryOptimizationModel")
        if not isinstance(self.headroom_schedule, MultiOpportunityHeadroomSchedule):
            raise TypeError(
                "headroom_schedule must be a MultiOpportunityHeadroomSchedule"
            )
        if self.headroom_schedule.source_input.battery_model is not self.battery_model:
            raise ValueError(
                "headroom schedule must preserve exact battery model identity"
            )
        object.__setattr__(
            self,
            "control_step_duration_seconds",
            _require_positive_seconds(self.control_step_duration_seconds),
        )


@dataclass(frozen=True, slots=True)
class MultiOpportunityCandidatePlanningResult:
    """Preserve source candidate, optional reservation, and final candidate.

    The unmodified path deliberately returns the original candidate output by
    identity.  A modified path creates one replacement first step only and
    preserves every future source step by exact identity.
    """

    source_input: MultiOpportunityCandidatePlanningInput
    source_candidate_output: OptimizationSolveOutput
    reservation_result: MultiOpportunityGridChargeReservationResult | None
    final_output: OptimizationSolveOutput

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, MultiOpportunityCandidatePlanningInput):
            raise TypeError(
                "source_input must be a MultiOpportunityCandidatePlanningInput"
            )
        if not isinstance(self.source_candidate_output, OptimizationSolveOutput):
            raise TypeError(
                "source_candidate_output must be an OptimizationSolveOutput"
            )
        if not isinstance(self.final_output, OptimizationSolveOutput):
            raise TypeError("final_output must be an OptimizationSolveOutput")
        if (
            self.source_candidate_output.result.source_problem
            is not self.source_input.problem
        ):
            raise ValueError("source candidate must preserve exact problem identity")
        if self.final_output.result.source_problem is not self.source_input.problem:
            raise ValueError("final output must preserve exact problem identity")
        if self.reservation_result is None:
            if self.final_output is not self.source_candidate_output:
                raise ValueError(
                    "unreserved planning must retain exact candidate output"
                )
            return
        self._validate_reservation()
        self._validate_final_output()

    def _validate_reservation(self) -> None:
        assert self.reservation_result is not None
        reservation_input = self.reservation_result.source_input
        if (
            reservation_input.headroom_schedule
            is not self.source_input.headroom_schedule
        ):
            raise ValueError(
                "reservation must preserve exact headroom schedule identity"
            )
        if reservation_input.battery_state is not self.source_input.battery_state:
            raise ValueError("reservation must preserve exact battery state identity")
        if reservation_input.battery_model is not self.source_input.battery_model:
            raise ValueError("reservation must preserve exact battery model identity")
        if (
            reservation_input.duration_seconds
            != self.source_input.control_step_duration_seconds
        ):
            raise ValueError("reservation must preserve exact duration semantics")
        candidate_steps = self.source_candidate_output.solution.steps
        if not candidate_steps:
            raise ValueError("reservation requires a current source candidate step")
        candidate = candidate_steps[0]
        if candidate.intent.action != "charge":
            raise ValueError("reservation requires a charging source candidate step")
        if (
            reservation_input.requested_grid_charge_power_kw
            != candidate.requested_power_kw
        ):
            raise ValueError("reservation request must equal source candidate power")

    def _validate_final_output(self) -> None:
        assert self.reservation_result is not None
        candidate = self.source_candidate_output
        final = self.final_output
        allowed = self.reservation_result.allowed_grid_charge_power_kw
        candidate_steps = candidate.solution.steps
        if allowed == candidate_steps[0].requested_power_kw:
            if final is not candidate:
                raise ValueError(
                    "unreduced reservation must retain candidate output identity"
                )
            return
        if final is candidate:
            raise ValueError("reduced reservation requires a distinct final output")
        if final.result.outcome != candidate.result.outcome:
            raise ValueError("final output must preserve source candidate outcome")
        final_steps = final.solution.steps
        if len(final_steps) != len(candidate_steps):
            raise ValueError("final output must preserve source candidate step count")
        for index in range(1, len(candidate_steps)):
            if final_steps[index] is not candidate_steps[index]:
                raise ValueError("future candidate steps must preserve exact identity")
        final_current = final_steps[0]
        if final_current.timestamp is not candidate_steps[0].timestamp:
            raise ValueError(
                "final current step must preserve exact timestamp identity"
            )
        if allowed == 0:
            if (
                final_current.intent.action != "idle"
                or final_current.requested_power_kw != 0
            ):
                raise ValueError("zero reservation allowance requires idle zero power")
        elif (
            final_current.intent.action != "charge"
            or final_current.requested_power_kw != allowed
        ):
            raise ValueError(
                "partial reservation must retain charge direction and allowance"
            )


class MultiOpportunityCandidatePlanningBoundary(ABC):
    """Define stateless current-step-only schedule-aware candidate planning."""

    __slots__ = ()

    @abstractmethod
    def plan(
        self,
        planning_input: MultiOpportunityCandidatePlanningInput,
    ) -> MultiOpportunityCandidatePlanningResult:
        """Return one source candidate and its optionally reservation-adjusted view."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class DeterministicMultiOpportunityCandidatePlanner(
    MultiOpportunityCandidatePlanningBoundary
):
    """Adjust only an exact cheap-grid current candidate using TASK-148 evidence."""

    candidate_optimizer: NetLoadAwareBaselineOptimizer
    reservation_calculator: MultiOpportunityGridChargeReservationBoundary

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_optimizer, NetLoadAwareBaselineOptimizer):
            raise TypeError(
                "candidate_optimizer must be a NetLoadAwareBaselineOptimizer"
            )
        if not isinstance(
            self.reservation_calculator,
            MultiOpportunityGridChargeReservationBoundary,
        ):
            raise TypeError(
                "reservation_calculator must be a "
                "MultiOpportunityGridChargeReservationBoundary"
            )

    def plan(
        self,
        planning_input: MultiOpportunityCandidatePlanningInput,
    ) -> MultiOpportunityCandidatePlanningResult:
        if not isinstance(planning_input, MultiOpportunityCandidatePlanningInput):
            raise TypeError(
                "planning_input must be a MultiOpportunityCandidatePlanningInput"
            )
        if self.candidate_optimizer.configuration is not planning_input.configuration:
            raise ValueError(
                "candidate optimizer must preserve exact configuration identity"
            )
        candidate_output = self.candidate_optimizer.solve_with_solution(
            planning_input.problem
        )
        if not self._is_cheap_grid_charge(planning_input, candidate_output):
            return MultiOpportunityCandidatePlanningResult(
                planning_input,
                candidate_output,
                None,
                candidate_output,
            )
        candidate_step = candidate_output.solution.steps[0]
        reservation = self.reservation_calculator.calculate(
            MultiOpportunityGridChargeReservationInput(
                planning_input.headroom_schedule,
                planning_input.battery_state,
                planning_input.battery_model,
                candidate_step.requested_power_kw,
                planning_input.control_step_duration_seconds,
            )
        )
        final_output = self._final_output(candidate_output, reservation)
        return MultiOpportunityCandidatePlanningResult(
            planning_input,
            candidate_output,
            reservation,
            final_output,
        )

    @staticmethod
    def _is_cheap_grid_charge(
        planning_input: MultiOpportunityCandidatePlanningInput,
        candidate_output: OptimizationSolveOutput,
    ) -> bool:
        steps = candidate_output.solution.steps
        if not steps:
            return False
        current_point = planning_input.problem.forecast_horizon.points[0]
        current_step = steps[0]
        return (
            current_step.intent.action == "charge"
            and current_point.pv_power_kw <= current_point.load_power_kw
        )

    @staticmethod
    def _final_output(
        candidate_output: OptimizationSolveOutput,
        reservation: MultiOpportunityGridChargeReservationResult,
    ) -> OptimizationSolveOutput:
        candidate_step = candidate_output.solution.steps[0]
        allowed = reservation.allowed_grid_charge_power_kw
        if allowed == candidate_step.requested_power_kw:
            return candidate_output
        intent = DecisionIntent("idle") if allowed == 0 else candidate_step.intent
        current_step = OptimizationSolutionStep(
            candidate_step.timestamp,
            intent,
            allowed,
        )
        result = OptimizationResult(
            candidate_output.result.source_problem,
            candidate_output.result.outcome,
        )
        solution = OptimizationSolution(
            result,
            (current_step, *candidate_output.solution.steps[1:]),
        )
        return OptimizationSolveOutput(result, solution)
