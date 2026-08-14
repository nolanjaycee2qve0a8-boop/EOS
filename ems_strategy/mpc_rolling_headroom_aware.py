"""One rolling-headroom-aware MPC cycle with physical explanation compatibility."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ems_strategy.decision import EMSDecision
from ems_strategy.mpc_current_action import (
    MPCCurrentAction,
    MPCCurrentActionExtractionBoundary,
    MPCDecisionTranslationBoundary,
    MPCDecisionTranslationInput,
)
from ems_strategy.mpc_physically_aware import (
    PhysicallyAwareMPCCycleInput,
    PhysicallyAwareMPCCycleResult,
)
from optimization import (
    BatteryOptimizationInput,
    OptimizationControlPlan,
    OptimizationProblem,
    OptimizationSolutionControlPlanConstructionBoundary,
    OptimizationSolutionControlPlanConstructionInput,
    PhysicallyAwareBaselineOptimizationInput,
    RollingHeadroomAwarePhysicalOptimizationBoundary,
    RollingHeadroomAwarePhysicalOptimizationSolveOutput,
)


@dataclass(frozen=True, slots=True)
class RollingHeadroomAwareMPCCycleResult:
    """Retain rolling-headroom, physical, and current-decision provenance."""

    source_input: PhysicallyAwareMPCCycleInput
    problem: OptimizationProblem
    battery_input: BatteryOptimizationInput
    physically_aware_input: PhysicallyAwareBaselineOptimizationInput
    rolling_headroom_optimization_output: (
        RollingHeadroomAwarePhysicalOptimizationSolveOutput
    )
    control_plan: OptimizationControlPlan
    current_action: MPCCurrentAction
    decision: EMSDecision
    physical_cycle_view: PhysicallyAwareMPCCycleResult

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, PhysicallyAwareMPCCycleInput):
            raise TypeError("source_input must be a PhysicallyAwareMPCCycleInput")
        if not isinstance(self.problem, OptimizationProblem):
            raise TypeError("problem must be an OptimizationProblem")
        if not isinstance(self.battery_input, BatteryOptimizationInput):
            raise TypeError("battery_input must be a BatteryOptimizationInput")
        if not isinstance(
            self.physically_aware_input, PhysicallyAwareBaselineOptimizationInput
        ):
            raise TypeError(
                "physically_aware_input must be a "
                "PhysicallyAwareBaselineOptimizationInput"
            )
        if not isinstance(
            self.rolling_headroom_optimization_output,
            RollingHeadroomAwarePhysicalOptimizationSolveOutput,
        ):
            raise TypeError(
                "rolling_headroom_optimization_output must be a "
                "RollingHeadroomAwarePhysicalOptimizationSolveOutput"
            )
        if not isinstance(self.control_plan, OptimizationControlPlan):
            raise TypeError("control_plan must be an OptimizationControlPlan")
        if not isinstance(self.current_action, MPCCurrentAction):
            raise TypeError("current_action must be an MPCCurrentAction")
        if not isinstance(self.decision, EMSDecision):
            raise TypeError("decision must be an EMSDecision")
        if not isinstance(self.physical_cycle_view, PhysicallyAwareMPCCycleResult):
            raise TypeError(
                "physical_cycle_view must be a PhysicallyAwareMPCCycleResult"
            )

        cycle = self.source_input.cycle_input
        if self.problem.context is not cycle.context:
            raise ValueError("problem must preserve exact input context identity")
        if self.problem.forecast_horizon is not cycle.forecast_horizon:
            raise ValueError("problem must preserve exact input forecast identity")
        if self.problem.objectives is not cycle.objectives:
            raise ValueError("problem must preserve exact input objectives identity")
        if self.battery_input.problem is not self.problem:
            raise ValueError("battery input must preserve exact problem identity")
        if self.battery_input.battery_state is not self.source_input.battery_state:
            raise ValueError("battery input must preserve exact state identity")
        if self.battery_input.battery_model is not self.source_input.battery_model:
            raise ValueError("battery input must preserve exact model identity")
        if self.physically_aware_input.battery_input is not self.battery_input:
            raise ValueError(
                "physical input must preserve exact battery input identity"
            )
        if (
            self.physically_aware_input.control_step_duration_seconds
            != cycle.configuration.control_step_duration_seconds
        ):
            raise ValueError("physical input must preserve MPC configuration duration")

        output = self.rolling_headroom_optimization_output
        physical_output = output.physical_output
        if output.source_input is not self.physically_aware_input:
            raise ValueError("rolling output must preserve exact physical input")
        if physical_output.source_input is not self.physically_aware_input:
            raise ValueError("physical output must preserve exact physical input")
        if (
            physical_output.candidate_output
            is not output.candidate_planning_result.final_output
        ):
            raise ValueError(
                "physical output must consume exact rolling final candidate"
            )
        if self.control_plan.source_result is not physical_output.final_output.result:
            raise ValueError("control plan must preserve exact physical final result")
        if self.current_action.source_plan is not self.control_plan:
            raise ValueError("current action must preserve exact control plan identity")
        if self.decision.source_context is not cycle.context:
            raise ValueError("decision must preserve exact input context identity")
        if self.decision.source_strategy is not cycle.source_strategy:
            raise ValueError("decision must preserve exact strategy identity")
        if self.decision.intent is not self.current_action.selected_step.intent:
            raise ValueError(
                "decision must preserve exact selected-step intent identity"
            )
        if (
            self.decision.requested_power_kw
            != self.current_action.selected_step.requested_power_kw
        ):
            raise ValueError("decision power must equal selected-step requested power")

        view = self.physical_cycle_view
        if view.source_input is not self.source_input:
            raise ValueError("physical cycle view must preserve exact source input")
        if view.problem is not self.problem:
            raise ValueError("physical cycle view must preserve exact problem identity")
        if view.battery_input is not self.battery_input:
            raise ValueError("physical cycle view must preserve exact battery input")
        if view.physically_aware_input is not self.physically_aware_input:
            raise ValueError("physical cycle view must preserve exact physical input")
        if view.optimization_output is not physical_output:
            raise ValueError("physical cycle view must preserve exact physical output")
        if view.control_plan is not self.control_plan:
            raise ValueError("physical cycle view must preserve exact control plan")
        if view.current_action is not self.current_action:
            raise ValueError("physical cycle view must preserve exact current action")
        if view.decision is not self.decision:
            raise ValueError("physical cycle view must preserve exact decision")


class RollingHeadroomAwareMPCCycleBoundary(ABC):
    """Define one stateless rolling-headroom-aware MPC planning cycle only."""

    __slots__ = ()

    @abstractmethod
    def run_cycle(
        self, cycle_input: PhysicallyAwareMPCCycleInput
    ) -> RollingHeadroomAwareMPCCycleResult:
        """Run one complete rolling-headroom planning-to-decision cycle."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class RollingHeadroomAwareSingleMPCCycleOrchestrator(
    RollingHeadroomAwareMPCCycleBoundary
):
    """Coordinate exactly one TASK-142 output into a current MPC decision."""

    rolling_headroom_optimization_boundary: (
        RollingHeadroomAwarePhysicalOptimizationBoundary
    )
    solution_plan_constructor: OptimizationSolutionControlPlanConstructionBoundary
    current_action_extractor: MPCCurrentActionExtractionBoundary
    decision_translator: MPCDecisionTranslationBoundary

    def __post_init__(self) -> None:
        if not isinstance(
            self.rolling_headroom_optimization_boundary,
            RollingHeadroomAwarePhysicalOptimizationBoundary,
        ):
            raise TypeError(
                "rolling_headroom_optimization_boundary must be a "
                "RollingHeadroomAwarePhysicalOptimizationBoundary"
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
            self.current_action_extractor, MPCCurrentActionExtractionBoundary
        ):
            raise TypeError(
                "current_action_extractor must be an MPCCurrentActionExtractionBoundary"
            )
        if not isinstance(self.decision_translator, MPCDecisionTranslationBoundary):
            raise TypeError(
                "decision_translator must be an MPCDecisionTranslationBoundary"
            )

    def run_cycle(
        self, cycle_input: PhysicallyAwareMPCCycleInput
    ) -> RollingHeadroomAwareMPCCycleResult:
        """Run each injected boundary once and stop on the first failure."""
        if not isinstance(cycle_input, PhysicallyAwareMPCCycleInput):
            raise TypeError("cycle_input must be a PhysicallyAwareMPCCycleInput")
        source_cycle = cycle_input.cycle_input
        problem = OptimizationProblem(
            source_cycle.context,
            source_cycle.forecast_horizon,
            source_cycle.objectives,
        )
        battery_input = BatteryOptimizationInput(
            problem,
            cycle_input.battery_state,
            cycle_input.battery_model,
        )
        physical_input = PhysicallyAwareBaselineOptimizationInput(
            battery_input,
            source_cycle.configuration.control_step_duration_seconds,
        )
        output = (
            self.rolling_headroom_optimization_boundary.solve_rolling_headroom_aware(
                physical_input
            )
        )
        self._require_output(output, physical_input)
        plan = self.solution_plan_constructor.construct(
            OptimizationSolutionControlPlanConstructionInput(
                output.physical_output.final_output.solution
            )
        )
        self._require_plan(plan, output)
        action = self.current_action_extractor.extract(plan)
        self._require_action(action, plan)
        decision = self.decision_translator.translate(
            MPCDecisionTranslationInput(action, source_cycle.source_strategy)
        )
        self._require_decision(decision)
        view = PhysicallyAwareMPCCycleResult(
            cycle_input,
            problem,
            battery_input,
            physical_input,
            output.physical_output,
            plan,
            action,
            decision,
        )
        return RollingHeadroomAwareMPCCycleResult(
            cycle_input,
            problem,
            battery_input,
            physical_input,
            output,
            plan,
            action,
            decision,
            view,
        )

    @staticmethod
    def _require_output(
        output: object,
        physical_input: PhysicallyAwareBaselineOptimizationInput,
    ) -> None:
        if not isinstance(output, RollingHeadroomAwarePhysicalOptimizationSolveOutput):
            raise TypeError(
                "rolling_headroom_optimization_boundary must return a "
                "RollingHeadroomAwarePhysicalOptimizationSolveOutput"
            )
        if output.source_input is not physical_input:
            raise ValueError("rolling output must preserve exact physical input")

    @staticmethod
    def _require_plan(
        plan: object,
        output: RollingHeadroomAwarePhysicalOptimizationSolveOutput,
    ) -> None:
        if not isinstance(plan, OptimizationControlPlan):
            raise TypeError(
                "solution_plan_constructor must return an OptimizationControlPlan"
            )
        if plan.source_result is not output.physical_output.final_output.result:
            raise ValueError("control plan must preserve exact physical final result")

    @staticmethod
    def _require_action(action: object, plan: OptimizationControlPlan) -> None:
        if not isinstance(action, MPCCurrentAction):
            raise TypeError("current_action_extractor must return an MPCCurrentAction")
        if action.source_plan is not plan:
            raise ValueError("current action must preserve exact control plan identity")

    @staticmethod
    def _require_decision(decision: object) -> None:
        if not isinstance(decision, EMSDecision):
            raise TypeError("decision_translator must return an EMSDecision")
