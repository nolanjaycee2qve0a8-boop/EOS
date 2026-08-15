"""One economic schedule-aware MPC cycle with physical compatibility evidence.

This TASK-159 adapter consumes TASK-158 exactly once.  It never inspects
prices, schedule entries, reservation results, or physical constraints; those
facts remain owned by the complete upstream economic physical output.
"""

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
    EconomicMultiOpportunityPhysicalOptimizationBoundary,
    EconomicMultiOpportunityPhysicalOptimizationInput,
    EconomicMultiOpportunityPhysicalOptimizationSolveOutput,
    NetLoadAwareBaselineOptimizationConfiguration,
    OptimizationControlPlan,
    OptimizationProblem,
    OptimizationSolutionControlPlanConstructionBoundary,
    OptimizationSolutionControlPlanConstructionInput,
    PhysicallyAwareOptimizationSolveOutput,
    PVOpportunityWindowConfiguration,
)


@dataclass(frozen=True, slots=True)
class EconomicMultiOpportunityMPCCycleInput:
    """Compose existing physical MPC facts with TASK-158 planning configuration."""

    physical_cycle_input: PhysicallyAwareMPCCycleInput
    candidate_configuration: NetLoadAwareBaselineOptimizationConfiguration
    opportunity_configuration: PVOpportunityWindowConfiguration

    def __post_init__(self) -> None:
        if not isinstance(self.physical_cycle_input, PhysicallyAwareMPCCycleInput):
            raise TypeError(
                "physical_cycle_input must be a PhysicallyAwareMPCCycleInput"
            )
        if not isinstance(
            self.candidate_configuration,
            NetLoadAwareBaselineOptimizationConfiguration,
        ):
            raise TypeError(
                "candidate_configuration must be a "
                "NetLoadAwareBaselineOptimizationConfiguration"
            )
        if not isinstance(
            self.opportunity_configuration,
            PVOpportunityWindowConfiguration,
        ):
            raise TypeError(
                "opportunity_configuration must be a PVOpportunityWindowConfiguration"
            )


@dataclass(frozen=True, slots=True)
class EconomicMultiOpportunityMPCCycleResult:
    """Retain TASK-158 evidence and one physical-final MPC decision chain."""

    source_input: EconomicMultiOpportunityMPCCycleInput
    economic_multi_opportunity_optimization_output: (
        EconomicMultiOpportunityPhysicalOptimizationSolveOutput
    )
    control_plan: OptimizationControlPlan
    current_action: MPCCurrentAction
    decision: EMSDecision
    physical_cycle_view: PhysicallyAwareMPCCycleResult

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, EconomicMultiOpportunityMPCCycleInput):
            raise TypeError(
                "source_input must be an EconomicMultiOpportunityMPCCycleInput"
            )
        if not isinstance(
            self.economic_multi_opportunity_optimization_output,
            EconomicMultiOpportunityPhysicalOptimizationSolveOutput,
        ):
            raise TypeError(
                "economic_multi_opportunity_optimization_output must be an "
                "EconomicMultiOpportunityPhysicalOptimizationSolveOutput"
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
        self._validate_economic_output()
        self._validate_current_decision()
        self._validate_compatibility_view()

    def _validate_economic_output(self) -> None:
        physical_cycle_input = self.source_input.physical_cycle_input
        cycle = physical_cycle_input.cycle_input
        output = self.economic_multi_opportunity_optimization_output
        optimization_input = output.source_input
        if optimization_input.problem.context is not cycle.context:
            raise ValueError("optimization input must preserve exact context identity")
        if optimization_input.problem.forecast_horizon is not cycle.forecast_horizon:
            raise ValueError("optimization input must preserve exact forecast identity")
        if optimization_input.problem.objectives is not cycle.objectives:
            raise ValueError(
                "optimization input must preserve exact objectives identity"
            )
        if (
            optimization_input.configuration
            is not self.source_input.candidate_configuration
        ):
            raise ValueError(
                "optimization input must preserve exact candidate "
                "configuration identity"
            )
        if optimization_input.battery_state is not physical_cycle_input.battery_state:
            raise ValueError("optimization input must preserve exact state identity")
        if optimization_input.battery_model is not physical_cycle_input.battery_model:
            raise ValueError("optimization input must preserve exact model identity")
        if (
            optimization_input.opportunity_configuration
            is not self.source_input.opportunity_configuration
        ):
            raise ValueError(
                "optimization input must preserve exact opportunity "
                "configuration identity"
            )
        if (
            optimization_input.control_step_duration_seconds
            != cycle.configuration.control_step_duration_seconds
        ):
            raise ValueError("optimization input must preserve MPC duration")

    def _validate_current_decision(self) -> None:
        cycle = self.source_input.physical_cycle_input.cycle_input
        physical_output = (
            self.economic_multi_opportunity_optimization_output.physical_output
        )
        if self.control_plan.source_result is not physical_output.final_output.result:
            raise ValueError("control plan must preserve exact physical final result")
        if self.current_action.source_plan is not self.control_plan:
            raise ValueError("current action must preserve exact control plan identity")
        if self.decision.source_context is not cycle.context:
            raise ValueError("decision must preserve exact input context identity")
        if self.decision.source_strategy is not cycle.source_strategy:
            raise ValueError("decision must preserve exact strategy identity")
        selected_step = self.current_action.selected_step
        if self.decision.intent is not selected_step.intent:
            raise ValueError(
                "decision must preserve exact selected-step intent identity"
            )
        if self.decision.requested_power_kw != selected_step.requested_power_kw:
            raise ValueError("decision power must equal selected-step requested power")

    def _validate_compatibility_view(self) -> None:
        output = self.economic_multi_opportunity_optimization_output
        physical_output = output.physical_output
        view = self.physical_cycle_view
        if view.source_input is not self.source_input.physical_cycle_input:
            raise ValueError("physical cycle view must preserve exact source input")
        if view.problem is not output.source_input.problem:
            raise ValueError("physical cycle view must preserve exact problem identity")
        if view.battery_input is not physical_output.source_input.battery_input:
            raise ValueError(
                "physical cycle view must preserve exact battery input identity"
            )
        if view.physically_aware_input is not physical_output.source_input:
            raise ValueError(
                "physical cycle view must preserve exact physical input identity"
            )
        if view.optimization_output is not physical_output:
            raise ValueError("physical cycle view must preserve exact physical output")
        if view.control_plan is not self.control_plan:
            raise ValueError("physical cycle view must preserve exact control plan")
        if view.current_action is not self.current_action:
            raise ValueError("physical cycle view must preserve exact current action")
        if view.decision is not self.decision:
            raise ValueError("physical cycle view must preserve exact decision")


class EconomicMultiOpportunityMPCCycleBoundary(ABC):
    """Define one stateless TASK-158 physical-final MPC planning cycle."""

    __slots__ = ()

    @abstractmethod
    def run_cycle(
        self,
        cycle_input: EconomicMultiOpportunityMPCCycleInput,
    ) -> EconomicMultiOpportunityMPCCycleResult:
        """Run one complete economic schedule-aware cycle without repetition."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class EconomicMultiOpportunitySingleMPCCycleOrchestrator(
    EconomicMultiOpportunityMPCCycleBoundary
):
    """Translate one exact TASK-158 physical final into one EMS decision."""

    economic_multi_opportunity_optimization_boundary: (
        EconomicMultiOpportunityPhysicalOptimizationBoundary
    )
    solution_plan_constructor: OptimizationSolutionControlPlanConstructionBoundary
    current_action_extractor: MPCCurrentActionExtractionBoundary
    decision_translator: MPCDecisionTranslationBoundary

    def __post_init__(self) -> None:
        if not isinstance(
            self.economic_multi_opportunity_optimization_boundary,
            EconomicMultiOpportunityPhysicalOptimizationBoundary,
        ):
            raise TypeError(
                "economic_multi_opportunity_optimization_boundary must be an "
                "EconomicMultiOpportunityPhysicalOptimizationBoundary"
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
        cycle_input: EconomicMultiOpportunityMPCCycleInput,
    ) -> EconomicMultiOpportunityMPCCycleResult:
        """Call each injected boundary once and stop on the first failure."""
        if not isinstance(cycle_input, EconomicMultiOpportunityMPCCycleInput):
            raise TypeError(
                "cycle_input must be an EconomicMultiOpportunityMPCCycleInput"
            )
        physical_cycle_input = cycle_input.physical_cycle_input
        source_cycle = physical_cycle_input.cycle_input
        problem = OptimizationProblem(
            source_cycle.context,
            source_cycle.forecast_horizon,
            source_cycle.objectives,
        )
        optimization_boundary = self.economic_multi_opportunity_optimization_boundary
        output = optimization_boundary.solve_economic_multi_opportunity(
            EconomicMultiOpportunityPhysicalOptimizationInput(
                problem,
                cycle_input.candidate_configuration,
                physical_cycle_input.battery_state,
                physical_cycle_input.battery_model,
                cycle_input.opportunity_configuration,
                source_cycle.configuration.control_step_duration_seconds,
            )
        )
        self._require_output(output, problem)
        physical_output = output.physical_output
        plan = self.solution_plan_constructor.construct(
            OptimizationSolutionControlPlanConstructionInput(
                physical_output.final_output.solution
            )
        )
        self._require_plan(plan, physical_output)
        action = self.current_action_extractor.extract(plan)
        self._require_action(action, plan)
        decision = self.decision_translator.translate(
            MPCDecisionTranslationInput(action, source_cycle.source_strategy)
        )
        self._require_decision(decision)
        physical_input = physical_output.source_input
        view = PhysicallyAwareMPCCycleResult(
            physical_cycle_input,
            problem,
            physical_input.battery_input,
            physical_input,
            physical_output,
            plan,
            action,
            decision,
        )
        return EconomicMultiOpportunityMPCCycleResult(
            cycle_input,
            output,
            plan,
            action,
            decision,
            view,
        )

    @staticmethod
    def _require_output(
        output: object,
        problem: OptimizationProblem,
    ) -> None:
        if not isinstance(
            output,
            EconomicMultiOpportunityPhysicalOptimizationSolveOutput,
        ):
            raise TypeError(
                "economic_multi_opportunity_optimization_boundary must return an "
                "EconomicMultiOpportunityPhysicalOptimizationSolveOutput"
            )
        if output.source_input.problem is not problem:
            raise ValueError("optimization output must preserve exact problem identity")

    @staticmethod
    def _require_plan(
        plan: object,
        physical_output: PhysicallyAwareOptimizationSolveOutput,
    ) -> None:
        if not isinstance(plan, OptimizationControlPlan):
            raise TypeError(
                "solution_plan_constructor must return an OptimizationControlPlan"
            )
        if plan.source_result is not physical_output.final_output.result:
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
