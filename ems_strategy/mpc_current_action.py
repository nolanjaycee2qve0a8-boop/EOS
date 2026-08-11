"""Explicit MPC current-action selection and decision-translation seams."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ems_strategy.decision import EMSDecision
from ems_strategy.descriptor import EMSStrategyDescriptor
from optimization import OptimizationControlPlan, OptimizationControlStep


@dataclass(frozen=True, slots=True)
class MPCCurrentAction:
    """Identify one exact current step from one exact proposed control plan.

    This artifact selects only one caller-provided plan step. It does not
    advance, execute, mutate, schedule, or otherwise consume future steps.
    """

    source_plan: OptimizationControlPlan
    selected_step: OptimizationControlStep

    def __post_init__(self) -> None:
        if not isinstance(self.source_plan, OptimizationControlPlan):
            raise TypeError("source_plan must be an OptimizationControlPlan")
        if not isinstance(self.selected_step, OptimizationControlStep):
            raise TypeError("selected_step must be an OptimizationControlStep")
        if not any(
            self.selected_step is plan_step for plan_step in self.source_plan.steps
        ):
            raise ValueError(
                "selected_step must preserve exact source plan step identity"
            )


class MPCCurrentActionExtractionBoundary(ABC):
    """Define stateless selection of one current action from one control plan."""

    __slots__ = ()

    @abstractmethod
    def extract(self, plan: OptimizationControlPlan) -> MPCCurrentAction:
        """Return one selected step without progressing or executing the plan."""
        raise NotImplementedError


class FirstStepMPCCurrentActionExtractor(MPCCurrentActionExtractionBoundary):
    """Select only the first caller-ordered control-plan step as current action.

    The first step rule is explicit. It is not clock matching, a scheduler,
    automatic time advancement, or a receding-horizon loop.
    """

    __slots__ = ()

    def extract(self, plan: OptimizationControlPlan) -> MPCCurrentAction:
        if not isinstance(plan, OptimizationControlPlan):
            raise TypeError("plan must be an OptimizationControlPlan")
        if not plan.steps:
            raise ValueError(
                "plan must contain at least one step to select current action"
            )
        return MPCCurrentAction(plan, plan.steps[0])


@dataclass(frozen=True, slots=True)
class MPCDecisionTranslationInput:
    """Preserve exact current-action and MPC descriptor provenance for translation."""

    current_action: MPCCurrentAction
    source_strategy: EMSStrategyDescriptor

    def __post_init__(self) -> None:
        if not isinstance(self.current_action, MPCCurrentAction):
            raise TypeError("current_action must be an MPCCurrentAction")
        if not isinstance(self.source_strategy, EMSStrategyDescriptor):
            raise TypeError("source_strategy must be an EMSStrategyDescriptor")


class MPCDecisionTranslationBoundary(ABC):
    """Define translation of one selected plan step into one current decision.

    A conforming implementation returns an existing ``EMSDecision`` with the
    exact context reached through the source-plan provenance and the exact
    caller-supplied MPC strategy descriptor. It does not create an execution
    input or perform feasibility evaluation.
    """

    __slots__ = ()

    @abstractmethod
    def translate(self, translation: MPCDecisionTranslationInput) -> EMSDecision:
        """Return the current semantic decision only."""
        raise NotImplementedError
