"""Gate one schedule-aware cheap-grid candidate with completed economics.

This TASK-157 path is deliberately parallel to TASK-149.  It consumes an
already-computed schedule and economic evidence, then may replace only the
first cheap-grid charging candidate.  PV-surplus charging, discharge, idle,
and every future candidate step remain outside this grid-arbitrage seam.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from decision_formation import DecisionIntent
from optimization.battery_planning import (
    BatteryOptimizationModel,
    BatteryOptimizationState,
)
from optimization.economic_grid_charge_value import (
    EconomicGridChargeValueBoundary,
    EconomicGridChargeValueInput,
    EconomicGridChargeValueResult,
)
from optimization.economic_planning import EconomicPlanningEvidence
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


@dataclass(frozen=True, slots=True)
class EconomicMultiOpportunityCandidatePlanningInput:
    """Retain caller-owned candidate facts plus completed physical/value evidence.

    The duration required by TASK-148 remains exact planning evidence already
    held by ``headroom_schedule.source_input``.  This contract intentionally
    does not add an independently supplied duration, forecast, or simulator
    fact that could diverge from the completed schedule.
    """

    problem: OptimizationProblem
    configuration: NetLoadAwareBaselineOptimizationConfiguration
    battery_state: BatteryOptimizationState
    battery_model: BatteryOptimizationModel
    headroom_schedule: MultiOpportunityHeadroomSchedule
    economic_planning_evidence: EconomicPlanningEvidence

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
        if not isinstance(self.economic_planning_evidence, EconomicPlanningEvidence):
            raise TypeError(
                "economic_planning_evidence must be an EconomicPlanningEvidence"
            )
        if (
            self.headroom_schedule.source_input.forecast_horizon
            is not self.problem.forecast_horizon
        ):
            raise ValueError(
                "headroom schedule must preserve exact problem forecast identity"
            )
        if self.headroom_schedule.source_input.battery_model is not self.battery_model:
            raise ValueError(
                "headroom schedule must preserve exact battery model identity"
            )
        economic_input = self.economic_planning_evidence.source_input
        if economic_input.forecast_horizon is not self.problem.forecast_horizon:
            raise ValueError(
                "economic evidence must preserve exact problem forecast identity"
            )
        if economic_input.battery_model is not self.battery_model:
            raise ValueError(
                "economic evidence must preserve exact battery model identity"
            )


@dataclass(frozen=True, slots=True)
class EconomicMultiOpportunityCandidatePlanningResult:
    """Preserve source candidate, optional gating evidence, and final candidate.

    No evidence means the candidate did not represent current cheap-grid
    charging and the original output is retained by exact identity.  A gated
    result can only replace index zero; all future candidate steps remain the
    exact source objects.
    """

    source_input: EconomicMultiOpportunityCandidatePlanningInput
    source_candidate_output: OptimizationSolveOutput
    reservation_result: MultiOpportunityGridChargeReservationResult | None
    economic_value_result: EconomicGridChargeValueResult | None
    final_output: OptimizationSolveOutput

    def __post_init__(self) -> None:
        if not isinstance(
            self.source_input,
            EconomicMultiOpportunityCandidatePlanningInput,
        ):
            raise TypeError(
                "source_input must be an EconomicMultiOpportunityCandidatePlanningInput"
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
        if self.reservation_result is None or self.economic_value_result is None:
            if (
                self.reservation_result is not None
                or self.economic_value_result is not None
            ):
                raise ValueError(
                    "reservation and economic value evidence must be supplied together"
                )
            if self.final_output is not self.source_candidate_output:
                raise ValueError("ungated planning must retain exact candidate output")
            return
        self._validate_reservation()
        self._validate_economic_value()
        self._validate_final_output()

    def _validate_reservation(self) -> None:
        assert self.reservation_result is not None
        reservation_input = self.reservation_result.source_input
        source = self.source_input
        if reservation_input.headroom_schedule is not source.headroom_schedule:
            raise ValueError(
                "reservation must preserve exact headroom schedule identity"
            )
        if reservation_input.battery_state is not source.battery_state:
            raise ValueError("reservation must preserve exact battery state identity")
        if reservation_input.battery_model is not source.battery_model:
            raise ValueError("reservation must preserve exact battery model identity")
        if (
            reservation_input.duration_seconds
            != source.headroom_schedule.source_input.control_step_duration_seconds
        ):
            raise ValueError("reservation must preserve exact schedule duration")
        steps = self.source_candidate_output.solution.steps
        if not steps or steps[0].intent.action != "charge":
            raise ValueError("reservation requires a charging source candidate step")
        if (
            reservation_input.requested_grid_charge_power_kw
            != steps[0].requested_power_kw
        ):
            raise ValueError("reservation request must equal source candidate power")

    def _validate_economic_value(self) -> None:
        assert self.reservation_result is not None
        assert self.economic_value_result is not None
        value_input = self.economic_value_result.source_input
        if value_input.reservation_result is not self.reservation_result:
            raise ValueError("economic value must preserve exact reservation identity")
        if (
            value_input.economic_planning_evidence
            is not self.source_input.economic_planning_evidence
        ):
            raise ValueError(
                "economic value must preserve exact economic evidence identity"
            )
        if value_input.current_source_index != 0:
            raise ValueError("economic value must use the current source index")

    def _validate_final_output(self) -> None:
        assert self.reservation_result is not None
        assert self.economic_value_result is not None
        candidate = self.source_candidate_output
        final = self.final_output
        candidate_steps = candidate.solution.steps
        if not candidate_steps:
            raise ValueError("gated planning requires a current source candidate step")
        supported = (
            self.economic_value_result.economically_supported_grid_charge_power_kw
        )
        allowed = self.reservation_result.allowed_grid_charge_power_kw
        requested = candidate_steps[0].requested_power_kw
        if supported > allowed or allowed > requested:
            raise ValueError("economics must only further restrict the source request")
        if supported == requested:
            if final is not candidate:
                raise ValueError(
                    "unreduced planning must retain candidate output identity"
                )
            return
        if final is candidate:
            raise ValueError("reduced planning requires a distinct final output")
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
        if supported == 0:
            if (
                final_current.intent.action != "idle"
                or final_current.requested_power_kw != 0
            ):
                raise ValueError("zero economic support requires idle zero power")
        elif (
            final_current.intent.action != "charge"
            or final_current.requested_power_kw != supported
        ):
            raise ValueError(
                "positive economic support must retain charge direction and power"
            )


class EconomicMultiOpportunityCandidatePlanningBoundary(ABC):
    """Define stateless current-step grid-arbitrage candidate planning."""

    __slots__ = ()

    @abstractmethod
    def plan(
        self,
        planning_input: EconomicMultiOpportunityCandidatePlanningInput,
    ) -> EconomicMultiOpportunityCandidatePlanningResult:
        """Return one candidate and its optional headroom/economic-gated view."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class DeterministicEconomicMultiOpportunityCandidatePlanner(
    EconomicMultiOpportunityCandidatePlanningBoundary
):
    """Compose one net-load candidate with completed reservation and economics."""

    candidate_optimizer: NetLoadAwareBaselineOptimizer
    reservation_calculator: MultiOpportunityGridChargeReservationBoundary
    economic_value_calculator: EconomicGridChargeValueBoundary

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
        if not isinstance(
            self.economic_value_calculator, EconomicGridChargeValueBoundary
        ):
            raise TypeError(
                "economic_value_calculator must be an EconomicGridChargeValueBoundary"
            )

    def plan(
        self,
        planning_input: EconomicMultiOpportunityCandidatePlanningInput,
    ) -> EconomicMultiOpportunityCandidatePlanningResult:
        if not isinstance(
            planning_input,
            EconomicMultiOpportunityCandidatePlanningInput,
        ):
            raise TypeError(
                "planning_input must be an "
                "EconomicMultiOpportunityCandidatePlanningInput"
            )
        if self.candidate_optimizer.configuration is not planning_input.configuration:
            raise ValueError(
                "candidate optimizer must preserve exact configuration identity"
            )
        candidate_output = self.candidate_optimizer.solve_with_solution(
            planning_input.problem
        )
        if not self._is_cheap_grid_charge(planning_input, candidate_output):
            return EconomicMultiOpportunityCandidatePlanningResult(
                planning_input,
                candidate_output,
                None,
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
                planning_input.headroom_schedule.source_input.control_step_duration_seconds,
            )
        )
        economic_value = self.economic_value_calculator.calculate(
            EconomicGridChargeValueInput(
                reservation,
                planning_input.economic_planning_evidence,
                0,
            )
        )
        final_output = self._final_output(candidate_output, economic_value)
        return EconomicMultiOpportunityCandidatePlanningResult(
            planning_input,
            candidate_output,
            reservation,
            economic_value,
            final_output,
        )

    @staticmethod
    def _is_cheap_grid_charge(
        planning_input: EconomicMultiOpportunityCandidatePlanningInput,
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
        economic_value: EconomicGridChargeValueResult,
    ) -> OptimizationSolveOutput:
        candidate_step = candidate_output.solution.steps[0]
        supported = economic_value.economically_supported_grid_charge_power_kw
        if supported == candidate_step.requested_power_kw:
            return candidate_output
        intent = DecisionIntent("idle") if supported == 0 else candidate_step.intent
        current_step = OptimizationSolutionStep(
            candidate_step.timestamp,
            intent,
            supported,
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
