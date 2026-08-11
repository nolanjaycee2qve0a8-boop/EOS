"""Deterministic representation mapping from solved values to EOS plans."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from optimization.control_plan import OptimizationControlPlan, OptimizationControlStep
from optimization.solution import OptimizationSolution


@dataclass(frozen=True, slots=True)
class OptimizationSolutionControlPlanConstructionInput:
    """Carry one exact caller-supplied solution into plan construction.

    The solution already carries exact result provenance, so this input does
    not duplicate that reference. It neither looks up nor derives a solution.
    """

    solution: OptimizationSolution

    def __post_init__(self) -> None:
        if not isinstance(self.solution, OptimizationSolution):
            raise TypeError("solution must be an OptimizationSolution")


class OptimizationSolutionControlPlanConstructionBoundary(ABC):
    """Define solution-aware construction of one EOS future control plan."""

    __slots__ = ()

    @abstractmethod
    def construct(
        self,
        construction_input: OptimizationSolutionControlPlanConstructionInput,
    ) -> OptimizationControlPlan:
        """Represent exact solved values as one EOS control plan."""
        raise NotImplementedError


class OptimizationSolutionControlPlanBuilder(
    OptimizationSolutionControlPlanConstructionBoundary
):
    """Map each solved value to exactly one EOS control-plan step.

    This is a stateless representation adapter. It preserves solution order,
    action object identity, requested-power magnitude, and source-result
    provenance; it does not solve, alter, or execute the proposed sequence.
    """

    __slots__ = ()

    def construct(
        self,
        construction_input: OptimizationSolutionControlPlanConstructionInput,
    ) -> OptimizationControlPlan:
        if not isinstance(
            construction_input,
            OptimizationSolutionControlPlanConstructionInput,
        ):
            raise TypeError(
                "construction_input must be an "
                "OptimizationSolutionControlPlanConstructionInput"
            )
        solution = construction_input.solution
        steps = tuple(
            OptimizationControlStep(
                step.timestamp,
                step.intent,
                step.requested_power_kw,
            )
            for step in solution.steps
        )
        return OptimizationControlPlan(solution.source_result, steps)
