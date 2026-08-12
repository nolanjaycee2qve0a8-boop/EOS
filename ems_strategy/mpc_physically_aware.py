"""One physically-aware MPC cycle preserving complete revision evidence."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ems_strategy.decision import EMSDecision
from ems_strategy.mpc_current_action import (
    MPCCurrentAction,
    MPCCurrentActionExtractionBoundary,
    MPCDecisionTranslationBoundary,
    MPCDecisionTranslationInput,
)
from ems_strategy.mpc_cycle import MPCCycleInput
from optimization import (
    BatteryOptimizationInput,
    BatteryOptimizationModel,
    BatteryOptimizationState,
    OptimizationControlPlan,
    OptimizationProblem,
    OptimizationSolutionControlPlanConstructionBoundary,
    OptimizationSolutionControlPlanConstructionInput,
    PhysicallyAwareBaselineOptimizationInput,
    PhysicallyAwareOptimizationBoundary,
    PhysicallyAwareOptimizationSolveOutput,
)


@dataclass(frozen=True, slots=True)
class PhysicallyAwareMPCCycleInput:
    """Compose one exact MPC cycle fact set with explicit battery planning facts."""

    cycle_input: MPCCycleInput
    battery_state: BatteryOptimizationState
    battery_model: BatteryOptimizationModel

    def __post_init__(self) -> None:
        if not isinstance(self.cycle_input, MPCCycleInput):
            raise TypeError("cycle_input must be an MPCCycleInput")
        if not isinstance(self.battery_state, BatteryOptimizationState):
            raise TypeError("battery_state must be a BatteryOptimizationState")
        if not isinstance(self.battery_model, BatteryOptimizationModel):
            raise TypeError("battery_model must be a BatteryOptimizationModel")


@dataclass(frozen=True, slots=True)
class PhysicallyAwareMPCCycleResult:
    """Retain all one-cycle physical revision and decision provenance exactly."""

    source_input: PhysicallyAwareMPCCycleInput
    problem: OptimizationProblem
    battery_input: BatteryOptimizationInput
    physically_aware_input: PhysicallyAwareBaselineOptimizationInput
    optimization_output: PhysicallyAwareOptimizationSolveOutput
    control_plan: OptimizationControlPlan
    current_action: MPCCurrentAction
    decision: EMSDecision

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, PhysicallyAwareMPCCycleInput):
            raise TypeError("source_input must be a PhysicallyAwareMPCCycleInput")
        if not isinstance(self.problem, OptimizationProblem):
            raise TypeError("problem must be an OptimizationProblem")
        if not isinstance(self.battery_input, BatteryOptimizationInput):
            raise TypeError("battery_input must be a BatteryOptimizationInput")
        if not isinstance(
            self.physically_aware_input,
            PhysicallyAwareBaselineOptimizationInput,
        ):
            raise TypeError(
                "physically_aware_input must be a "
                "PhysicallyAwareBaselineOptimizationInput"
            )
        if not isinstance(
            self.optimization_output,
            PhysicallyAwareOptimizationSolveOutput,
        ):
            raise TypeError(
                "optimization_output must be a PhysicallyAwareOptimizationSolveOutput"
            )
        if not isinstance(self.control_plan, OptimizationControlPlan):
            raise TypeError("control_plan must be an OptimizationControlPlan")
        if not isinstance(self.current_action, MPCCurrentAction):
            raise TypeError("current_action must be an MPCCurrentAction")
        if not isinstance(self.decision, EMSDecision):
            raise TypeError("decision must be an EMSDecision")

        cycle_input = self.source_input.cycle_input
        if self.problem.context is not cycle_input.context:
            raise ValueError("problem must preserve exact input context identity")
        if self.problem.forecast_horizon is not cycle_input.forecast_horizon:
            raise ValueError("problem must preserve exact input forecast identity")
        if self.problem.objectives is not cycle_input.objectives:
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
            != cycle_input.configuration.control_step_duration_seconds
        ):
            raise ValueError("physical input must preserve MPC configuration duration")
        if self.optimization_output.source_input is not self.physically_aware_input:
            raise ValueError("optimization output must preserve exact physical input")
        final_output = self.optimization_output.final_output
        if self.control_plan.source_result is not final_output.result:
            raise ValueError("control plan must preserve exact final result identity")
        if self.current_action.source_plan is not self.control_plan:
            raise ValueError("current action must preserve exact control plan identity")
        if self.decision.source_context is not cycle_input.context:
            raise ValueError("decision must preserve exact input context identity")
        if self.decision.source_strategy is not cycle_input.source_strategy:
            raise ValueError("decision must preserve exact strategy identity")
        selected_step = self.current_action.selected_step
        if self.decision.intent is not selected_step.intent:
            raise ValueError(
                "decision must preserve exact selected-step intent identity"
            )
        if self.decision.requested_power_kw != selected_step.requested_power_kw:
            raise ValueError("decision power must equal selected-step requested power")


class PhysicallyAwareMPCCycleBoundary(ABC):
    """Define one stateless physically-aware MPC integration cycle only."""

    __slots__ = ()

    @abstractmethod
    def run_cycle(
        self,
        cycle_input: PhysicallyAwareMPCCycleInput,
    ) -> PhysicallyAwareMPCCycleResult:
        """Run one planning-to-decision cycle and stop without repetition."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class PhysicallyAwareSingleMPCCycleOrchestrator(PhysicallyAwareMPCCycleBoundary):
    """Coordinate exactly one caller-composed physical MPC planning cycle."""

    physically_aware_optimization_boundary: PhysicallyAwareOptimizationBoundary
    solution_plan_constructor: OptimizationSolutionControlPlanConstructionBoundary
    current_action_extractor: MPCCurrentActionExtractionBoundary
    decision_translator: MPCDecisionTranslationBoundary

    def __post_init__(self) -> None:
        if not isinstance(
            self.physically_aware_optimization_boundary,
            PhysicallyAwareOptimizationBoundary,
        ):
            raise TypeError(
                "physically_aware_optimization_boundary must be a "
                "PhysicallyAwareOptimizationBoundary"
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

    def run_cycle(
        self,
        cycle_input: PhysicallyAwareMPCCycleInput,
    ) -> PhysicallyAwareMPCCycleResult:
        """Run each injected stage once, stopping immediately on any failure."""
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
        output = self.physically_aware_optimization_boundary.solve_physically(
            physical_input
        )
        self._require_output(output, physical_input)
        # Only the physically revised final solution is eligible for execution planning.
        plan = self.solution_plan_constructor.construct(
            OptimizationSolutionControlPlanConstructionInput(
                output.final_output.solution
            )
        )
        self._require_plan(plan, output)
        action = self.current_action_extractor.extract(plan)
        self._require_action(action, plan)
        decision = self.decision_translator.translate(
            MPCDecisionTranslationInput(action, source_cycle.source_strategy)
        )
        self._require_decision(decision)
        return PhysicallyAwareMPCCycleResult(
            cycle_input,
            problem,
            battery_input,
            physical_input,
            output,
            plan,
            action,
            decision,
        )

    @staticmethod
    def _require_output(
        output: object,
        physical_input: PhysicallyAwareBaselineOptimizationInput,
    ) -> None:
        if not isinstance(output, PhysicallyAwareOptimizationSolveOutput):
            raise TypeError(
                "physically_aware_optimization_boundary must return a "
                "PhysicallyAwareOptimizationSolveOutput"
            )
        if output.source_input is not physical_input:
            raise ValueError("optimization output must preserve exact physical input")

    @staticmethod
    def _require_plan(
        plan: object,
        output: PhysicallyAwareOptimizationSolveOutput,
    ) -> None:
        if not isinstance(plan, OptimizationControlPlan):
            raise TypeError(
                "solution_plan_constructor must return an OptimizationControlPlan"
            )
        if plan.source_result is not output.final_output.result:
            raise ValueError("control plan must preserve exact final result identity")

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
