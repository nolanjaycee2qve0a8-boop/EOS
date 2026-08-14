"""Compose rolling headroom evidence with existing candidate and physical seams.

This is deliberately parallel to the TASK-136 full-horizon path.  It consumes
TASK-141's selected-opportunity evidence without changing TASK-132 accounting,
TASK-134 candidate planning, or TASK-135 physical revision.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from optimization.headroom_aware_candidate_planning import (
    HeadroomAwareCandidatePlanningBoundary,
    HeadroomAwareCandidatePlanningInput,
    HeadroomAwareCandidatePlanningResult,
)
from optimization.physically_aware_baseline import (
    ExplicitCandidatePhysicalRevisionBoundary,
    ExplicitCandidatePhysicalRevisionInput,
    PhysicallyAwareBaselineOptimizationInput,
    PhysicallyAwareOptimizationSolveOutput,
)
from optimization.pv_opportunity_window import PVOpportunityWindowConfiguration
from optimization.rolling_pv_headroom import (
    RollingPVHeadroomRequirement,
    RollingPVHeadroomRequirementBoundary,
    RollingPVHeadroomRequirementInput,
)


@dataclass(frozen=True, slots=True)
class RollingHeadroomAwarePhysicalOptimizationSolveOutput:
    """Retain full forecast, rolling selection, candidate, and physical evidence."""

    source_input: PhysicallyAwareBaselineOptimizationInput
    rolling_headroom_requirement: RollingPVHeadroomRequirement
    candidate_planning_result: HeadroomAwareCandidatePlanningResult
    physical_output: PhysicallyAwareOptimizationSolveOutput

    def __post_init__(self) -> None:
        if not isinstance(
            self.source_input,
            PhysicallyAwareBaselineOptimizationInput,
        ):
            raise TypeError(
                "source_input must be a PhysicallyAwareBaselineOptimizationInput"
            )
        if not isinstance(
            self.rolling_headroom_requirement,
            RollingPVHeadroomRequirement,
        ):
            raise TypeError(
                "rolling_headroom_requirement must be a RollingPVHeadroomRequirement"
            )
        if not isinstance(
            self.candidate_planning_result,
            HeadroomAwareCandidatePlanningResult,
        ):
            raise TypeError(
                "candidate_planning_result must be a "
                "HeadroomAwareCandidatePlanningResult"
            )
        if not isinstance(
            self.physical_output,
            PhysicallyAwareOptimizationSolveOutput,
        ):
            raise TypeError(
                "physical_output must be a PhysicallyAwareOptimizationSolveOutput"
            )
        self._validate_rolling_provenance()
        self._validate_candidate_provenance()
        self._validate_physical_provenance()

    def _validate_rolling_provenance(self) -> None:
        battery_input = self.source_input.battery_input
        rolling = self.rolling_headroom_requirement
        rolling_input = rolling.source_input
        if rolling_input.forecast_horizon is not battery_input.problem.forecast_horizon:
            raise ValueError(
                "rolling headroom must preserve exact full source forecast identity"
            )
        if rolling_input.battery_model is not battery_input.battery_model:
            raise ValueError(
                "rolling headroom must preserve exact source battery model identity"
            )
        if (
            rolling_input.control_step_duration_seconds
            != self.source_input.control_step_duration_seconds
        ):
            raise ValueError("rolling headroom must preserve the exact duration")
        requirement_input = rolling.headroom_requirement.source_input
        if requirement_input.forecast_horizon is not rolling.selected_forecast_horizon:
            raise ValueError(
                "inner headroom must preserve exact selected horizon identity"
            )
        if requirement_input.battery_model is not battery_input.battery_model:
            raise ValueError(
                "inner headroom must preserve exact source battery model identity"
            )
        if (
            requirement_input.control_step_duration_seconds
            != self.source_input.control_step_duration_seconds
        ):
            raise ValueError("inner headroom must preserve the exact duration")

    def _validate_candidate_provenance(self) -> None:
        planning_input = self.candidate_planning_result.source_input
        if planning_input.battery_input is not self.source_input.battery_input:
            raise ValueError(
                "candidate planning must preserve exact source battery input identity"
            )
        if (
            planning_input.headroom_requirement
            is not self.rolling_headroom_requirement.headroom_requirement
        ):
            raise ValueError(
                "candidate planning must preserve exact inner headroom identity"
            )
        if (
            planning_input.control_step_duration_seconds
            != self.source_input.control_step_duration_seconds
        ):
            raise ValueError("candidate planning must preserve the exact duration")

    def _validate_physical_provenance(self) -> None:
        if self.physical_output.source_input is not self.source_input:
            raise ValueError(
                "physical output must preserve exact source input identity"
            )
        if (
            self.physical_output.candidate_output
            is not self.candidate_planning_result.final_output
        ):
            raise ValueError(
                "physical output must revise the exact rolling planned candidate"
            )


class RollingHeadroomAwarePhysicalOptimizationBoundary(ABC):
    """Define one rolling-headroom candidate-to-physical composition seam."""

    __slots__ = ()

    @abstractmethod
    def solve_rolling_headroom_aware(
        self,
        optimization_input: PhysicallyAwareBaselineOptimizationInput,
    ) -> RollingHeadroomAwarePhysicalOptimizationSolveOutput:
        """Compose rolling headroom, planning, and physical revision once each."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class DeterministicRollingHeadroomAwarePhysicalOptimizer(
    RollingHeadroomAwarePhysicalOptimizationBoundary
):
    """Call injected TASK-141, TASK-134, and TASK-135 seams exactly once."""

    rolling_headroom_calculator: RollingPVHeadroomRequirementBoundary
    candidate_planner: HeadroomAwareCandidatePlanningBoundary
    explicit_physical_reviser: ExplicitCandidatePhysicalRevisionBoundary
    window_configuration: PVOpportunityWindowConfiguration

    def __post_init__(self) -> None:
        if not isinstance(
            self.rolling_headroom_calculator,
            RollingPVHeadroomRequirementBoundary,
        ):
            raise TypeError(
                "rolling_headroom_calculator must be a "
                "RollingPVHeadroomRequirementBoundary"
            )
        if not isinstance(
            self.candidate_planner,
            HeadroomAwareCandidatePlanningBoundary,
        ):
            raise TypeError(
                "candidate_planner must be a HeadroomAwareCandidatePlanningBoundary"
            )
        if not isinstance(
            self.explicit_physical_reviser,
            ExplicitCandidatePhysicalRevisionBoundary,
        ):
            raise TypeError(
                "explicit_physical_reviser must be an "
                "ExplicitCandidatePhysicalRevisionBoundary"
            )
        if not isinstance(self.window_configuration, PVOpportunityWindowConfiguration):
            raise TypeError(
                "window_configuration must be a PVOpportunityWindowConfiguration"
            )

    def solve_rolling_headroom_aware(
        self,
        optimization_input: PhysicallyAwareBaselineOptimizationInput,
    ) -> RollingHeadroomAwarePhysicalOptimizationSolveOutput:
        if not isinstance(
            optimization_input,
            PhysicallyAwareBaselineOptimizationInput,
        ):
            raise TypeError(
                "optimization_input must be a PhysicallyAwareBaselineOptimizationInput"
            )
        battery_input = optimization_input.battery_input
        rolling_requirement = self.rolling_headroom_calculator.calculate(
            RollingPVHeadroomRequirementInput(
                battery_input.problem.forecast_horizon,
                battery_input.battery_model,
                optimization_input.control_step_duration_seconds,
                self.window_configuration,
            )
        )
        candidate_planning_result = self.candidate_planner.plan(
            HeadroomAwareCandidatePlanningInput(
                battery_input,
                rolling_requirement.headroom_requirement,
                optimization_input.control_step_duration_seconds,
            )
        )
        physical_output = self.explicit_physical_reviser.revise(
            ExplicitCandidatePhysicalRevisionInput(
                optimization_input,
                candidate_planning_result.final_output,
            )
        )
        return RollingHeadroomAwarePhysicalOptimizationSolveOutput(
            optimization_input,
            rolling_requirement,
            candidate_planning_result,
            physical_output,
        )
