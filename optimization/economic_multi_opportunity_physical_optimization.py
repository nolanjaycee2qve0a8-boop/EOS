"""Compose economic schedule-aware candidate planning with physical revision.

This TASK-158 module owns one orchestration pass only.  TASK-147 derives the
multi-opportunity schedule, TASK-155 derives economic evidence, TASK-157
gates the current cheap-grid candidate, and TASK-135 applies the existing
physical revision.  No stage is reimplemented or retried here.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import isfinite

from optimization.battery_planning import (
    BatteryOptimizationInput,
    BatteryOptimizationModel,
    BatteryOptimizationState,
)
from optimization.economic_multi_opportunity_candidate_planning import (
    EconomicMultiOpportunityCandidatePlanningBoundary,
    EconomicMultiOpportunityCandidatePlanningInput,
    EconomicMultiOpportunityCandidatePlanningResult,
)
from optimization.economic_planning import (
    EconomicPlanningBoundary,
    EconomicPlanningEvidence,
    EconomicPlanningInput,
)
from optimization.model import OptimizationProblem
from optimization.multi_opportunity_headroom_schedule import (
    MultiOpportunityHeadroomSchedule,
    MultiOpportunityHeadroomScheduleBoundary,
    MultiOpportunityHeadroomScheduleInput,
)
from optimization.net_load_aware_baseline import (
    NetLoadAwareBaselineOptimizationConfiguration,
)
from optimization.physically_aware_baseline import (
    ExplicitCandidatePhysicalRevisionBoundary,
    ExplicitCandidatePhysicalRevisionInput,
    PhysicallyAwareBaselineOptimizationInput,
    PhysicallyAwareOptimizationSolveOutput,
)
from optimization.pv_opportunity_window import PVOpportunityWindowConfiguration


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
class EconomicMultiOpportunityPhysicalOptimizationInput:
    """Retain exact caller-owned facts for one economic physical composition.

    Duration is explicit because TASK-147 and TASK-135 convert semantic power
    into energy over a caller-owned control interval.  It is never inferred
    from forecast timestamps or a clock.
    """

    problem: OptimizationProblem
    configuration: NetLoadAwareBaselineOptimizationConfiguration
    battery_state: BatteryOptimizationState
    battery_model: BatteryOptimizationModel
    opportunity_configuration: PVOpportunityWindowConfiguration
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
        if not isinstance(
            self.opportunity_configuration,
            PVOpportunityWindowConfiguration,
        ):
            raise TypeError(
                "opportunity_configuration must be a PVOpportunityWindowConfiguration"
            )
        object.__setattr__(
            self,
            "control_step_duration_seconds",
            _require_positive_seconds(self.control_step_duration_seconds),
        )


@dataclass(frozen=True, slots=True)
class EconomicMultiOpportunityPhysicalOptimizationSolveOutput:
    """Retain the complete economic candidate-to-physical evidence chain."""

    source_input: EconomicMultiOpportunityPhysicalOptimizationInput
    headroom_schedule: MultiOpportunityHeadroomSchedule
    economic_planning_evidence: EconomicPlanningEvidence
    candidate_planning_result: EconomicMultiOpportunityCandidatePlanningResult
    physical_output: PhysicallyAwareOptimizationSolveOutput

    def __post_init__(self) -> None:
        if not isinstance(
            self.source_input,
            EconomicMultiOpportunityPhysicalOptimizationInput,
        ):
            raise TypeError(
                "source_input must be an "
                "EconomicMultiOpportunityPhysicalOptimizationInput"
            )
        if not isinstance(self.headroom_schedule, MultiOpportunityHeadroomSchedule):
            raise TypeError(
                "headroom_schedule must be a MultiOpportunityHeadroomSchedule"
            )
        if not isinstance(self.economic_planning_evidence, EconomicPlanningEvidence):
            raise TypeError(
                "economic_planning_evidence must be an EconomicPlanningEvidence"
            )
        if not isinstance(
            self.candidate_planning_result,
            EconomicMultiOpportunityCandidatePlanningResult,
        ):
            raise TypeError(
                "candidate_planning_result must be an "
                "EconomicMultiOpportunityCandidatePlanningResult"
            )
        if not isinstance(
            self.physical_output,
            PhysicallyAwareOptimizationSolveOutput,
        ):
            raise TypeError(
                "physical_output must be a PhysicallyAwareOptimizationSolveOutput"
            )
        self._validate_schedule_provenance()
        self._validate_economic_provenance()
        self._validate_candidate_provenance()
        self._validate_physical_provenance()

    def _validate_schedule_provenance(self) -> None:
        schedule_input = self.headroom_schedule.source_input
        source = self.source_input
        if schedule_input.forecast_horizon is not source.problem.forecast_horizon:
            raise ValueError("schedule must preserve exact source forecast identity")
        if schedule_input.battery_model is not source.battery_model:
            raise ValueError(
                "schedule must preserve exact source battery model identity"
            )
        if (
            schedule_input.opportunity_configuration
            is not source.opportunity_configuration
        ):
            raise ValueError(
                "schedule must preserve exact opportunity configuration identity"
            )
        if (
            schedule_input.control_step_duration_seconds
            != source.control_step_duration_seconds
        ):
            raise ValueError("schedule must preserve exact duration semantics")

    def _validate_economic_provenance(self) -> None:
        economic_input = self.economic_planning_evidence.source_input
        source = self.source_input
        if economic_input.forecast_horizon is not source.problem.forecast_horizon:
            raise ValueError("economics must preserve exact source forecast identity")
        if economic_input.battery_model is not source.battery_model:
            raise ValueError(
                "economics must preserve exact source battery model identity"
            )

    def _validate_candidate_provenance(self) -> None:
        planning_input = self.candidate_planning_result.source_input
        source = self.source_input
        if planning_input.problem is not source.problem:
            raise ValueError("candidate planning must preserve exact problem identity")
        if planning_input.configuration is not source.configuration:
            raise ValueError(
                "candidate planning must preserve exact configuration identity"
            )
        if planning_input.battery_state is not source.battery_state:
            raise ValueError(
                "candidate planning must preserve exact battery state identity"
            )
        if planning_input.battery_model is not source.battery_model:
            raise ValueError(
                "candidate planning must preserve exact battery model identity"
            )
        if planning_input.headroom_schedule is not self.headroom_schedule:
            raise ValueError("candidate planning must preserve exact schedule identity")
        if (
            planning_input.economic_planning_evidence
            is not self.economic_planning_evidence
        ):
            raise ValueError("candidate planning must preserve exact economic evidence")

    def _validate_physical_provenance(self) -> None:
        physical_input = self.physical_output.source_input
        battery_input = physical_input.battery_input
        source = self.source_input
        if battery_input.problem is not source.problem:
            raise ValueError("physical revision must preserve exact problem identity")
        if battery_input.battery_state is not source.battery_state:
            raise ValueError(
                "physical revision must preserve exact battery state identity"
            )
        if battery_input.battery_model is not source.battery_model:
            raise ValueError(
                "physical revision must preserve exact battery model identity"
            )
        if (
            physical_input.control_step_duration_seconds
            != source.control_step_duration_seconds
        ):
            raise ValueError("physical revision must preserve exact duration semantics")
        if (
            self.physical_output.candidate_output
            is not self.candidate_planning_result.final_output
        ):
            raise ValueError(
                "physical revision must receive exact economic final candidate identity"
            )


class EconomicMultiOpportunityPhysicalOptimizationBoundary(ABC):
    """Define one schedule/economic/candidate/physical composition seam."""

    __slots__ = ()

    @abstractmethod
    def solve_economic_multi_opportunity(
        self,
        optimization_input: EconomicMultiOpportunityPhysicalOptimizationInput,
    ) -> EconomicMultiOpportunityPhysicalOptimizationSolveOutput:
        """Compose each injected stage once without re-solving or execution."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class DeterministicEconomicMultiOpportunityPhysicalOptimizer(
    EconomicMultiOpportunityPhysicalOptimizationBoundary
):
    """Call TASK-147, TASK-155, TASK-157, and TASK-135 exactly once each."""

    schedule_calculator: MultiOpportunityHeadroomScheduleBoundary
    economic_calculator: EconomicPlanningBoundary
    candidate_planner: EconomicMultiOpportunityCandidatePlanningBoundary
    explicit_physical_reviser: ExplicitCandidatePhysicalRevisionBoundary

    def __post_init__(self) -> None:
        if not isinstance(
            self.schedule_calculator,
            MultiOpportunityHeadroomScheduleBoundary,
        ):
            raise TypeError(
                "schedule_calculator must be a MultiOpportunityHeadroomScheduleBoundary"
            )
        if not isinstance(self.economic_calculator, EconomicPlanningBoundary):
            raise TypeError("economic_calculator must be an EconomicPlanningBoundary")
        if not isinstance(
            self.candidate_planner,
            EconomicMultiOpportunityCandidatePlanningBoundary,
        ):
            raise TypeError(
                "candidate_planner must be an "
                "EconomicMultiOpportunityCandidatePlanningBoundary"
            )
        if not isinstance(
            self.explicit_physical_reviser,
            ExplicitCandidatePhysicalRevisionBoundary,
        ):
            raise TypeError(
                "explicit_physical_reviser must be an "
                "ExplicitCandidatePhysicalRevisionBoundary"
            )

    def solve_economic_multi_opportunity(
        self,
        optimization_input: EconomicMultiOpportunityPhysicalOptimizationInput,
    ) -> EconomicMultiOpportunityPhysicalOptimizationSolveOutput:
        if not isinstance(
            optimization_input,
            EconomicMultiOpportunityPhysicalOptimizationInput,
        ):
            raise TypeError(
                "optimization_input must be an "
                "EconomicMultiOpportunityPhysicalOptimizationInput"
            )
        schedule = self.schedule_calculator.calculate(
            MultiOpportunityHeadroomScheduleInput(
                optimization_input.problem.forecast_horizon,
                optimization_input.battery_model,
                optimization_input.control_step_duration_seconds,
                optimization_input.opportunity_configuration,
            )
        )
        economics = self.economic_calculator.calculate(
            EconomicPlanningInput(
                optimization_input.problem.forecast_horizon,
                optimization_input.battery_model,
            )
        )
        candidate_result = self.candidate_planner.plan(
            EconomicMultiOpportunityCandidatePlanningInput(
                optimization_input.problem,
                optimization_input.configuration,
                optimization_input.battery_state,
                optimization_input.battery_model,
                schedule,
                economics,
            )
        )
        physical_input = PhysicallyAwareBaselineOptimizationInput(
            BatteryOptimizationInput(
                optimization_input.problem,
                optimization_input.battery_state,
                optimization_input.battery_model,
            ),
            optimization_input.control_step_duration_seconds,
        )
        physical_output = self.explicit_physical_reviser.revise(
            ExplicitCandidatePhysicalRevisionInput(
                physical_input,
                candidate_result.final_output,
            )
        )
        return EconomicMultiOpportunityPhysicalOptimizationSolveOutput(
            optimization_input,
            schedule,
            economics,
            candidate_result,
            physical_output,
        )
