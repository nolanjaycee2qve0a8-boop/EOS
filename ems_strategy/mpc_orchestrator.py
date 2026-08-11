"""Deterministic one-cycle orchestration of caller-supplied MPC seams."""

from dataclasses import dataclass

from ems_strategy.decision import EMSDecision
from ems_strategy.mpc_current_action import (
    MPCCurrentAction,
    MPCCurrentActionExtractionBoundary,
    MPCDecisionTranslationBoundary,
    MPCDecisionTranslationInput,
)
from ems_strategy.mpc_cycle import MPCCycleBoundary, MPCCycleInput, MPCCycleResult
from optimization import (
    OptimizationBoundary,
    OptimizationControlPlan,
    OptimizationControlPlanConstructionBoundary,
    OptimizationControlPlanConstructionInput,
    OptimizationProblem,
    OptimizationResult,
)


@dataclass(frozen=True, slots=True)
class SingleMPCCycleOrchestrator(MPCCycleBoundary):
    """Coordinate exactly one MPC cycle through explicit caller-owned seams.

    Dependencies are immutable references supplied by the caller; they are not
    selected, created, cached, or used as retained execution state. One call
    builds one problem, invokes each dependency once in sequence, and stops
    with one ``MPCCycleResult``. It neither repeats the horizon nor reaches
    feasibility, Actuation, physical execution, Runtime, or Device layers.
    """

    optimization_boundary: OptimizationBoundary
    plan_constructor: OptimizationControlPlanConstructionBoundary
    current_action_extractor: MPCCurrentActionExtractionBoundary
    decision_translator: MPCDecisionTranslationBoundary

    def __post_init__(self) -> None:
        if not isinstance(self.optimization_boundary, OptimizationBoundary):
            raise TypeError("optimization_boundary must be an OptimizationBoundary")
        if not isinstance(
            self.plan_constructor,
            OptimizationControlPlanConstructionBoundary,
        ):
            raise TypeError(
                "plan_constructor must be an "
                "OptimizationControlPlanConstructionBoundary"
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

    def run_cycle(self, cycle_input: MPCCycleInput) -> MPCCycleResult:
        """Run one explicit cycle and propagate the first dependency exception."""
        if not isinstance(cycle_input, MPCCycleInput):
            raise TypeError("cycle_input must be an MPCCycleInput")

        problem = OptimizationProblem(
            cycle_input.context,
            cycle_input.forecast_horizon,
            cycle_input.objectives,
        )
        optimization_result = self.optimization_boundary.solve(problem)
        self._require_optimization_result(optimization_result, problem)

        control_plan = self.plan_constructor.construct(
            OptimizationControlPlanConstructionInput(optimization_result)
        )
        self._require_control_plan(control_plan, optimization_result)

        current_action = self.current_action_extractor.extract(control_plan)
        self._require_current_action(current_action, control_plan)

        decision = self.decision_translator.translate(
            MPCDecisionTranslationInput(
                current_action,
                cycle_input.source_strategy,
            )
        )
        self._require_decision(decision)

        return MPCCycleResult(
            cycle_input,
            problem,
            optimization_result,
            control_plan,
            current_action,
            decision,
        )

    @staticmethod
    def _require_optimization_result(
        result: object,
        problem: OptimizationProblem,
    ) -> None:
        if not isinstance(result, OptimizationResult):
            raise TypeError("optimization_boundary must return an OptimizationResult")
        if result.source_problem is not problem:
            raise ValueError("optimization result must preserve exact problem identity")

    @staticmethod
    def _require_control_plan(
        plan: object,
        optimization_result: OptimizationResult,
    ) -> None:
        if not isinstance(plan, OptimizationControlPlan):
            raise TypeError("plan_constructor must return an OptimizationControlPlan")
        if plan.source_result is not optimization_result:
            raise ValueError(
                "control plan must preserve exact optimization result identity"
            )

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
