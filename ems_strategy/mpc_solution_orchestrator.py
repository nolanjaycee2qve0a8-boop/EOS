"""Caller-composed solution-aware orchestration for one explicit MPC cycle."""

from dataclasses import dataclass

from ems_strategy.decision import EMSDecision
from ems_strategy.mpc_current_action import (
    MPCCurrentAction,
    MPCCurrentActionExtractionBoundary,
    MPCDecisionTranslationBoundary,
    MPCDecisionTranslationInput,
)
from ems_strategy.mpc_cycle import MPCCycleInput
from ems_strategy.mpc_solution_cycle import (
    MPCSolutionCycleBoundary,
    MPCSolutionCycleResult,
)
from optimization import (
    OptimizationControlPlan,
    OptimizationProblem,
    OptimizationResult,
    OptimizationSolutionBoundary,
    OptimizationSolutionControlPlanConstructionBoundary,
    OptimizationSolutionControlPlanConstructionInput,
    OptimizationSolveOutput,
)


@dataclass(frozen=True, slots=True)
class SolutionAwareSingleMPCCycleOrchestrator(MPCSolutionCycleBoundary):
    """Coordinate one Result-and-Solution MPC cycle through injected seams.

    Each dependency is an immutable caller-owned reference. One invocation
    creates one problem, invokes every dependency at most once in order, and
    stops after one result. It neither repeats, advances, nor executes a plan.
    """

    optimization_solution_boundary: OptimizationSolutionBoundary
    solution_plan_constructor: OptimizationSolutionControlPlanConstructionBoundary
    current_action_extractor: MPCCurrentActionExtractionBoundary
    decision_translator: MPCDecisionTranslationBoundary

    def __post_init__(self) -> None:
        if not isinstance(
            self.optimization_solution_boundary,
            OptimizationSolutionBoundary,
        ):
            raise TypeError(
                "optimization_solution_boundary must be an OptimizationSolutionBoundary"
            )
        if not isinstance(
            self.solution_plan_constructor,
            OptimizationSolutionControlPlanConstructionBoundary,
        ):
            raise TypeError(
                "solution_plan_constructor must be an "
                "OptimizationSolutionControlPlanConstructionBoundary"
            )
        if not isinstance(
            self.current_action_extractor,
            MPCCurrentActionExtractionBoundary,
        ):
            raise TypeError(
                "current_action_extractor must be an MPCCurrentActionExtractionBoundary"
            )
        if not isinstance(self.decision_translator, MPCDecisionTranslationBoundary):
            raise TypeError(
                "decision_translator must be an MPCDecisionTranslationBoundary"
            )

    def run_cycle(self, cycle_input: MPCCycleInput) -> MPCSolutionCycleResult:
        """Run one cycle, propagating the first failure without retry."""
        if not isinstance(cycle_input, MPCCycleInput):
            raise TypeError("cycle_input must be an MPCCycleInput")

        problem = OptimizationProblem(
            cycle_input.context,
            cycle_input.forecast_horizon,
            cycle_input.objectives,
        )
        solve_output = self.optimization_solution_boundary.solve_with_solution(problem)
        self._require_solve_output(solve_output, problem)

        control_plan = self.solution_plan_constructor.construct(
            OptimizationSolutionControlPlanConstructionInput(solve_output.solution)
        )
        self._require_control_plan(control_plan, solve_output.result)

        current_action = self.current_action_extractor.extract(control_plan)
        self._require_current_action(current_action, control_plan)

        decision = self.decision_translator.translate(
            MPCDecisionTranslationInput(
                current_action,
                cycle_input.source_strategy,
            )
        )
        self._require_decision(decision)

        return MPCSolutionCycleResult(
            cycle_input,
            problem,
            solve_output,
            solve_output.result,
            solve_output.solution,
            control_plan,
            current_action,
            decision,
        )

    @staticmethod
    def _require_solve_output(
        solve_output: object,
        problem: OptimizationProblem,
    ) -> None:
        if not isinstance(solve_output, OptimizationSolveOutput):
            raise TypeError(
                "optimization_solution_boundary must return an OptimizationSolveOutput"
            )
        if solve_output.result.source_problem is not problem:
            raise ValueError("solve output must preserve exact problem identity")
        if solve_output.solution.source_result is not solve_output.result:
            raise ValueError("solve output must preserve exact result identity")

    @staticmethod
    def _require_control_plan(
        plan: object,
        optimization_result: OptimizationResult,
    ) -> None:
        if not isinstance(plan, OptimizationControlPlan):
            raise TypeError(
                "solution_plan_constructor must return an OptimizationControlPlan"
            )
        if plan.source_result is not optimization_result:
            raise ValueError("control plan must preserve exact result identity")

    @staticmethod
    def _require_current_action(
        action: object,
        control_plan: OptimizationControlPlan,
    ) -> None:
        if not isinstance(action, MPCCurrentAction):
            raise TypeError("current_action_extractor must return an MPCCurrentAction")
        if action.source_plan is not control_plan:
            raise ValueError("current action must preserve exact control plan identity")

    @staticmethod
    def _require_decision(decision: object) -> None:
        if not isinstance(decision, EMSDecision):
            raise TypeError("decision_translator must return an EMSDecision")
