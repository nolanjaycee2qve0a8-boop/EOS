"""Compose headroom-aware candidate planning with one physical revision.

This seam owns neither candidate rules nor physical correction.  It passes one
caller-owned planning request through the existing TASK-132, TASK-134, and
TASK-135 boundaries exactly once and retains all three stages as evidence.
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
from optimization.pv_headroom import (
    PVHeadroomRequirement,
    PVHeadroomRequirementBoundary,
    PVHeadroomRequirementInput,
)


@dataclass(frozen=True, slots=True)
class HeadroomAwarePhysicalOptimizationSolveOutput:
    """Retain exact TASK-132, TASK-134, and TASK-135 evidence artifacts."""

    source_input: PhysicallyAwareBaselineOptimizationInput
    headroom_requirement: PVHeadroomRequirement
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
        if not isinstance(self.headroom_requirement, PVHeadroomRequirement):
            raise TypeError("headroom_requirement must be a PVHeadroomRequirement")
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

        battery_input = self.source_input.battery_input
        requirement_input = self.headroom_requirement.source_input
        if (
            requirement_input.forecast_horizon
            is not battery_input.problem.forecast_horizon
        ):
            raise ValueError(
                "headroom requirement must preserve exact source forecast identity"
            )
        if requirement_input.battery_model is not battery_input.battery_model:
            raise ValueError(
                "headroom requirement must preserve exact source battery model identity"
            )
        if (
            requirement_input.control_step_duration_seconds
            != self.source_input.control_step_duration_seconds
        ):
            raise ValueError("headroom requirement must preserve the exact duration")

        planning_input = self.candidate_planning_result.source_input
        if planning_input.battery_input is not battery_input:
            raise ValueError(
                "candidate planning must preserve exact source battery input identity"
            )
        if planning_input.headroom_requirement is not self.headroom_requirement:
            raise ValueError(
                "candidate planning must preserve exact headroom requirement identity"
            )
        if (
            planning_input.control_step_duration_seconds
            != self.source_input.control_step_duration_seconds
        ):
            raise ValueError("candidate planning must preserve the exact duration")

        if self.physical_output.source_input is not self.source_input:
            raise ValueError(
                "physical output must preserve exact source input identity"
            )
        if (
            self.physical_output.candidate_output
            is not self.candidate_planning_result.final_output
        ):
            raise ValueError(
                "physical output must revise the exact headroom-aware final output"
            )


class HeadroomAwarePhysicalOptimizationBoundary(ABC):
    """Define one headroom-aware candidate-to-physical-evidence composition."""

    __slots__ = ()

    @abstractmethod
    def solve_headroom_aware(
        self,
        optimization_input: PhysicallyAwareBaselineOptimizationInput,
    ) -> HeadroomAwarePhysicalOptimizationSolveOutput:
        """Compose one requirement, one candidate plan, and one physical revision."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class DeterministicHeadroomAwarePhysicalOptimizer(
    HeadroomAwarePhysicalOptimizationBoundary
):
    """Call each injected TASK-132/134/135 dependency exactly once."""

    headroom_calculator: PVHeadroomRequirementBoundary
    candidate_planner: HeadroomAwareCandidatePlanningBoundary
    explicit_physical_reviser: ExplicitCandidatePhysicalRevisionBoundary

    def __post_init__(self) -> None:
        if not isinstance(self.headroom_calculator, PVHeadroomRequirementBoundary):
            raise TypeError(
                "headroom_calculator must be a PVHeadroomRequirementBoundary"
            )
        if not isinstance(
            self.candidate_planner, HeadroomAwareCandidatePlanningBoundary
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

    def solve_headroom_aware(
        self,
        optimization_input: PhysicallyAwareBaselineOptimizationInput,
    ) -> HeadroomAwarePhysicalOptimizationSolveOutput:
        if not isinstance(
            optimization_input,
            PhysicallyAwareBaselineOptimizationInput,
        ):
            raise TypeError(
                "optimization_input must be a PhysicallyAwareBaselineOptimizationInput"
            )
        battery_input = optimization_input.battery_input
        requirement = self.headroom_calculator.calculate(
            PVHeadroomRequirementInput(
                battery_input.problem.forecast_horizon,
                battery_input.battery_model,
                optimization_input.control_step_duration_seconds,
            )
        )
        candidate_planning_result = self.candidate_planner.plan(
            HeadroomAwareCandidatePlanningInput(
                battery_input,
                requirement,
                optimization_input.control_step_duration_seconds,
            )
        )
        physical_output = self.explicit_physical_reviser.revise(
            ExplicitCandidatePhysicalRevisionInput(
                optimization_input,
                candidate_planning_result.final_output,
            )
        )
        return HeadroomAwarePhysicalOptimizationSolveOutput(
            optimization_input,
            requirement,
            candidate_planning_result,
            physical_output,
        )
