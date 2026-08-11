"""One explicit, non-repeating MPC cycle provenance contract."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ems_strategy.context import EMSContext
from ems_strategy.decision import EMSDecision
from ems_strategy.descriptor import EMSStrategyDescriptor
from ems_strategy.mpc import MPCConfiguration
from ems_strategy.mpc_current_action import MPCCurrentAction
from forecast import ForecastHorizon
from optimization import (
    OptimizationControlPlan,
    OptimizationObjectiveCollection,
    OptimizationProblem,
    OptimizationResult,
)


@dataclass(frozen=True, slots=True)
class MPCCycleInput:
    """Preserve caller-owned facts for one explicit MPC planning cycle.

    This input is a fact and provenance carrier only. It neither builds an
    optimization problem nor refreshes a forecast, advances time, or retains
    any state for a later cycle.
    """

    context: EMSContext
    forecast_horizon: ForecastHorizon
    configuration: MPCConfiguration
    objectives: OptimizationObjectiveCollection
    source_strategy: EMSStrategyDescriptor

    def __post_init__(self) -> None:
        if not isinstance(self.context, EMSContext):
            raise TypeError("context must be an EMSContext")
        if not isinstance(self.forecast_horizon, ForecastHorizon):
            raise TypeError("forecast_horizon must be a ForecastHorizon")
        if not isinstance(self.configuration, MPCConfiguration):
            raise TypeError("configuration must be an MPCConfiguration")
        if not isinstance(self.objectives, OptimizationObjectiveCollection):
            raise TypeError("objectives must be an OptimizationObjectiveCollection")
        if not isinstance(self.source_strategy, EMSStrategyDescriptor):
            raise TypeError("source_strategy must be an EMSStrategyDescriptor")
        if (
            len(self.forecast_horizon.points)
            != self.configuration.forecast_horizon_points
        ):
            raise ValueError(
                "forecast_horizon point count must equal forecast_horizon_points"
            )


@dataclass(frozen=True, slots=True)
class MPCCycleResult:
    """Trace one successful MPC cycle without owning repetition or execution.

    The result preserves each exact artifact in the one-cycle provenance
    chain. It records neither a future action execution nor a next cycle.
    """

    source_input: MPCCycleInput
    problem: OptimizationProblem
    optimization_result: OptimizationResult
    control_plan: OptimizationControlPlan
    current_action: MPCCurrentAction
    decision: EMSDecision

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, MPCCycleInput):
            raise TypeError("source_input must be an MPCCycleInput")
        if not isinstance(self.problem, OptimizationProblem):
            raise TypeError("problem must be an OptimizationProblem")
        if not isinstance(self.optimization_result, OptimizationResult):
            raise TypeError("optimization_result must be an OptimizationResult")
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
        if self.optimization_result.source_problem is not self.problem:
            raise ValueError("optimization_result must preserve exact problem identity")
        if self.control_plan.source_result is not self.optimization_result:
            raise ValueError(
                "control_plan must preserve exact optimization result identity"
            )
        if self.current_action.source_plan is not self.control_plan:
            raise ValueError("current_action must preserve exact control plan identity")
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


class MPCCycleBoundary(ABC):
    """Define one stateless MPC cycle without a scheduler or hidden loop.

    A conforming implementation may coordinate caller-supplied seams once,
    but must stop after emitting one ``MPCCycleResult``. This boundary does
    not own solver selection, plan construction, current-action extraction,
    translation, feasibility, actuation, or simulation.
    """

    __slots__ = ()

    @abstractmethod
    def run_cycle(self, cycle_input: MPCCycleInput) -> MPCCycleResult:
        """Return one traceable outcome for one caller-supplied cycle input."""
        raise NotImplementedError
