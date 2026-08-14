"""Compose TASK-147 schedule, TASK-149 candidate, and TASK-135 revision once.

This parallel composition owns orchestration only.  It neither derives PV
opportunities nor performs cheap-grid reservation or physical correction; each
of those responsibilities remains in its established boundary.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import isfinite

from optimization.battery_planning import (
    BatteryOptimizationInput,
    BatteryOptimizationModel,
    BatteryOptimizationState,
)
from optimization.model import OptimizationProblem
from optimization.multi_opportunity_candidate_planning import (
    MultiOpportunityCandidatePlanningBoundary,
    MultiOpportunityCandidatePlanningInput,
    MultiOpportunityCandidatePlanningResult,
)
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
class MultiOpportunityPhysicalOptimizationInput:
    """Retain exact facts needed by the parallel schedule-aware composition."""

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
class MultiOpportunityPhysicalOptimizationSolveOutput:
    """Retain complete schedule, candidate, and physical provenance unchanged."""

    source_input: MultiOpportunityPhysicalOptimizationInput
    headroom_schedule: MultiOpportunityHeadroomSchedule
    candidate_planning_result: MultiOpportunityCandidatePlanningResult
    physical_output: PhysicallyAwareOptimizationSolveOutput

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, MultiOpportunityPhysicalOptimizationInput):
            raise TypeError(
                "source_input must be a MultiOpportunityPhysicalOptimizationInput"
            )
        if not isinstance(self.headroom_schedule, MultiOpportunityHeadroomSchedule):
            raise TypeError(
                "headroom_schedule must be a MultiOpportunityHeadroomSchedule"
            )
        if not isinstance(
            self.candidate_planning_result,
            MultiOpportunityCandidatePlanningResult,
        ):
            raise TypeError(
                "candidate_planning_result must be a "
                "MultiOpportunityCandidatePlanningResult"
            )
        if not isinstance(
            self.physical_output,
            PhysicallyAwareOptimizationSolveOutput,
        ):
            raise TypeError(
                "physical_output must be a PhysicallyAwareOptimizationSolveOutput"
            )
        self._validate_schedule_provenance()
        self._validate_candidate_provenance()
        self._validate_physical_provenance()

    def _validate_schedule_provenance(self) -> None:
        schedule_input = self.headroom_schedule.source_input
        if (
            schedule_input.forecast_horizon
            is not self.source_input.problem.forecast_horizon
        ):
            raise ValueError("schedule must preserve exact source forecast identity")
        if schedule_input.battery_model is not self.source_input.battery_model:
            raise ValueError(
                "schedule must preserve exact source battery model identity"
            )
        if (
            schedule_input.opportunity_configuration
            is not self.source_input.opportunity_configuration
        ):
            raise ValueError(
                "schedule must preserve exact opportunity configuration identity"
            )
        if (
            schedule_input.control_step_duration_seconds
            != self.source_input.control_step_duration_seconds
        ):
            raise ValueError("schedule must preserve exact duration semantics")

    def _validate_candidate_provenance(self) -> None:
        planning_input = self.candidate_planning_result.source_input
        if planning_input.problem is not self.source_input.problem:
            raise ValueError("candidate planning must preserve exact problem identity")
        if planning_input.configuration is not self.source_input.configuration:
            raise ValueError(
                "candidate planning must preserve exact configuration identity"
            )
        if planning_input.battery_state is not self.source_input.battery_state:
            raise ValueError(
                "candidate planning must preserve exact battery state identity"
            )
        if planning_input.battery_model is not self.source_input.battery_model:
            raise ValueError(
                "candidate planning must preserve exact battery model identity"
            )
        if planning_input.headroom_schedule is not self.headroom_schedule:
            raise ValueError("candidate planning must preserve exact schedule identity")
        if (
            planning_input.control_step_duration_seconds
            != self.source_input.control_step_duration_seconds
        ):
            raise ValueError(
                "candidate planning must preserve exact duration semantics"
            )

    def _validate_physical_provenance(self) -> None:
        physical_input = self.physical_output.source_input
        battery_input = physical_input.battery_input
        if battery_input.problem is not self.source_input.problem:
            raise ValueError("physical revision must preserve exact problem identity")
        if battery_input.battery_state is not self.source_input.battery_state:
            raise ValueError(
                "physical revision must preserve exact battery state identity"
            )
        if battery_input.battery_model is not self.source_input.battery_model:
            raise ValueError(
                "physical revision must preserve exact battery model identity"
            )
        if (
            physical_input.control_step_duration_seconds
            != self.source_input.control_step_duration_seconds
        ):
            raise ValueError("physical revision must preserve exact duration semantics")
        if (
            self.physical_output.candidate_output
            is not self.candidate_planning_result.final_output
        ):
            raise ValueError(
                "physical revision must receive exact planned final candidate identity"
            )


class MultiOpportunityPhysicalOptimizationBoundary(ABC):
    """Define one schedule-aware candidate-to-physical composition seam."""

    __slots__ = ()

    @abstractmethod
    def solve_multi_opportunity(
        self,
        optimization_input: MultiOpportunityPhysicalOptimizationInput,
    ) -> MultiOpportunityPhysicalOptimizationSolveOutput:
        """Compose one schedule, one candidate plan, and one physical revision."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class DeterministicMultiOpportunityPhysicalOptimizer(
    MultiOpportunityPhysicalOptimizationBoundary
):
    """Call injected TASK-147, TASK-149, and TASK-135 seams exactly once."""

    schedule_calculator: MultiOpportunityHeadroomScheduleBoundary
    candidate_planner: MultiOpportunityCandidatePlanningBoundary
    explicit_physical_reviser: ExplicitCandidatePhysicalRevisionBoundary

    def __post_init__(self) -> None:
        if not isinstance(
            self.schedule_calculator,
            MultiOpportunityHeadroomScheduleBoundary,
        ):
            raise TypeError(
                "schedule_calculator must be a MultiOpportunityHeadroomScheduleBoundary"
            )
        if not isinstance(
            self.candidate_planner,
            MultiOpportunityCandidatePlanningBoundary,
        ):
            raise TypeError(
                "candidate_planner must be a MultiOpportunityCandidatePlanningBoundary"
            )
        if not isinstance(
            self.explicit_physical_reviser,
            ExplicitCandidatePhysicalRevisionBoundary,
        ):
            raise TypeError(
                "explicit_physical_reviser must be an "
                "ExplicitCandidatePhysicalRevisionBoundary"
            )

    def solve_multi_opportunity(
        self,
        optimization_input: MultiOpportunityPhysicalOptimizationInput,
    ) -> MultiOpportunityPhysicalOptimizationSolveOutput:
        if not isinstance(
            optimization_input,
            MultiOpportunityPhysicalOptimizationInput,
        ):
            raise TypeError(
                "optimization_input must be a MultiOpportunityPhysicalOptimizationInput"
            )
        schedule = self.schedule_calculator.calculate(
            MultiOpportunityHeadroomScheduleInput(
                optimization_input.problem.forecast_horizon,
                optimization_input.battery_model,
                optimization_input.control_step_duration_seconds,
                optimization_input.opportunity_configuration,
            )
        )
        candidate_result = self.candidate_planner.plan(
            MultiOpportunityCandidatePlanningInput(
                optimization_input.problem,
                optimization_input.configuration,
                optimization_input.battery_state,
                optimization_input.battery_model,
                schedule,
                optimization_input.control_step_duration_seconds,
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
        return MultiOpportunityPhysicalOptimizationSolveOutput(
            optimization_input,
            schedule,
            candidate_result,
            physical_output,
        )
