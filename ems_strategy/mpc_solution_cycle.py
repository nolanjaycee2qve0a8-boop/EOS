"""One solution-aware MPC cycle provenance contract without repetition."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ems_strategy.decision import EMSDecision
from ems_strategy.mpc_current_action import MPCCurrentAction
from ems_strategy.mpc_cycle import MPCCycleInput
from optimization import (
    OptimizationControlPlan,
    OptimizationProblem,
    OptimizationResult,
    OptimizationSolution,
    OptimizationSolveOutput,
)


@dataclass(frozen=True, slots=True)
class MPCSolutionCycleResult:
    """Record every exact artifact in one solution-aware MPC cycle."""

    source_input: MPCCycleInput
    problem: OptimizationProblem
    solve_output: OptimizationSolveOutput
    optimization_result: OptimizationResult
    optimization_solution: OptimizationSolution
    control_plan: OptimizationControlPlan
    current_action: MPCCurrentAction
    decision: EMSDecision

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, MPCCycleInput):
            raise TypeError("source_input must be an MPCCycleInput")
        if not isinstance(self.problem, OptimizationProblem):
            raise TypeError("problem must be an OptimizationProblem")
        if not isinstance(self.solve_output, OptimizationSolveOutput):
            raise TypeError("solve_output must be an OptimizationSolveOutput")
        if not isinstance(self.optimization_result, OptimizationResult):
            raise TypeError("optimization_result must be an OptimizationResult")
        if not isinstance(self.optimization_solution, OptimizationSolution):
            raise TypeError("optimization_solution must be an OptimizationSolution")
        if not isinstance(self.control_plan, OptimizationControlPlan):
            raise TypeError("control_plan must be an OptimizationControlPlan")
        if not isinstance(self.current_action, MPCCurrentAction):
            raise TypeError("current_action must be an MPCCurrentAction")
        if not isinstance(self.decision, EMSDecision):
            raise TypeError("decision must be an EMSDecision")

        if self.problem.context is not self.source_input.context:
            raise ValueError("problem must preserve exact input context identity")
        if self.problem.forecast_horizon is not self.source_input.forecast_horizon:
            raise ValueError("problem must preserve exact input forecast identity")
        if self.problem.objectives is not self.source_input.objectives:
            raise ValueError("problem must preserve exact input objectives identity")
        if self.solve_output.result is not self.optimization_result:
            raise ValueError("solve output must preserve exact result identity")
        if self.solve_output.solution is not self.optimization_solution:
            raise ValueError("solve output must preserve exact solution identity")
        if self.optimization_result.source_problem is not self.problem:
            raise ValueError("optimization result must preserve exact problem identity")
        if self.optimization_solution.source_result is not self.optimization_result:
            raise ValueError(
                "optimization solution must preserve exact result identity"
            )
        if self.control_plan.source_result is not self.optimization_result:
            raise ValueError("control plan must preserve exact result identity")
        if self.current_action.source_plan is not self.control_plan:
            raise ValueError("current action must preserve exact control plan identity")
        if self.decision.source_context is not self.source_input.context:
            raise ValueError("decision must preserve exact input context identity")
        if self.decision.source_strategy is not self.source_input.source_strategy:
            raise ValueError("decision must preserve exact strategy identity")
        selected_step = self.current_action.selected_step
        if self.decision.intent is not selected_step.intent:
            raise ValueError(
                "decision must preserve exact selected-step intent identity"
            )
        if self.decision.requested_power_kw != selected_step.requested_power_kw:
            raise ValueError("decision power must equal selected-step requested power")


class MPCSolutionCycleBoundary(ABC):
    """Define one stateless solution-aware MPC cycle without repetition."""

    __slots__ = ()

    @abstractmethod
    def run_cycle(self, cycle_input: MPCCycleInput) -> MPCSolutionCycleResult:
        """Return one traceable solution-aware cycle and then stop."""
        raise NotImplementedError
