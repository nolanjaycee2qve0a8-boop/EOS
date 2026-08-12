"""Read-only machine-readable explanation of one physical MPC decision."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from decision_formation import DecisionIntent
from ems_strategy.decision import EMSDecision
from ems_strategy.mpc_physically_aware import PhysicallyAwareMPCCycleResult
from optimization import (
    BatteryPowerConstraintViolationKind,
    BatterySOCConstraintViolationKind,
    BatterySolutionRevisionReason,
    BatterySolutionRevisionStep,
    OptimizationSolutionStep,
)


@dataclass(frozen=True, slots=True)
class MPCDecisionExplanationInput:
    """Preserve one exact completed physical MPC cycle for read-only explanation."""

    cycle_result: PhysicallyAwareMPCCycleResult

    def __post_init__(self) -> None:
        if not isinstance(self.cycle_result, PhysicallyAwareMPCCycleResult):
            raise TypeError("cycle_result must be a PhysicallyAwareMPCCycleResult")


@dataclass(frozen=True, slots=True)
class MPCDecisionPhysicalExplanation:
    """Organize exact selected-step physical evidence without recomputation."""

    candidate_step: OptimizationSolutionStep
    final_step: OptimizationSolutionStep
    revision_step: BatterySolutionRevisionStep
    revision_reasons: tuple[BatterySolutionRevisionReason, ...]
    candidate_soc_violation_kinds: tuple[BatterySOCConstraintViolationKind, ...]
    candidate_power_violation_kinds: tuple[BatteryPowerConstraintViolationKind, ...]
    candidate_battery_horizon_feasible: bool
    final_soc_feasible: bool
    final_power_feasible: bool
    final_battery_horizon_feasible: bool
    candidate_starting_soc_fraction: float
    candidate_ending_soc_fraction: float
    final_starting_soc_fraction: float
    final_ending_soc_fraction: float
    min_soc_fraction: float
    max_soc_fraction: float
    max_charge_power_kw: float
    max_discharge_power_kw: float

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_step, OptimizationSolutionStep):
            raise TypeError("candidate_step must be an OptimizationSolutionStep")
        if not isinstance(self.final_step, OptimizationSolutionStep):
            raise TypeError("final_step must be an OptimizationSolutionStep")
        if not isinstance(self.revision_step, BatterySolutionRevisionStep):
            raise TypeError("revision_step must be a BatterySolutionRevisionStep")
        if self.revision_step.source_candidate_step is not self.candidate_step:
            raise ValueError(
                "revision step must preserve exact candidate step identity"
            )
        if self.revision_step.revised_step is not self.final_step:
            raise ValueError("revision step must preserve exact final step identity")
        if not isinstance(self.revision_reasons, tuple):
            raise TypeError("revision_reasons must be a tuple")
        if self.revision_reasons is not self.revision_step.reasons:
            raise ValueError(
                "revision reasons must preserve exact source tuple identity"
            )
        if not isinstance(self.candidate_soc_violation_kinds, tuple):
            raise TypeError("candidate_soc_violation_kinds must be a tuple")
        if not isinstance(self.candidate_power_violation_kinds, tuple):
            raise TypeError("candidate_power_violation_kinds must be a tuple")
        if any(
            kind not in ("below_min_soc", "above_max_soc")
            for kind in self.candidate_soc_violation_kinds
        ):
            raise ValueError("candidate SOC violation kinds must be valid")
        if any(
            kind not in ("charge_power_above_max", "discharge_power_above_max")
            for kind in self.candidate_power_violation_kinds
        ):
            raise ValueError("candidate power violation kinds must be valid")
        for field_name in (
            "candidate_battery_horizon_feasible",
            "final_soc_feasible",
            "final_power_feasible",
            "final_battery_horizon_feasible",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be a bool")


@dataclass(frozen=True, slots=True)
class MPCDecisionExplanation:
    """Expose one exact current decision and its relevant physical evidence."""

    source_input: MPCDecisionExplanationInput
    selected_step_index: int
    decision: EMSDecision
    candidate_action: DecisionIntent
    candidate_requested_power_kw: float
    final_action: DecisionIntent
    final_requested_power_kw: float
    revision_applied: bool
    physical_explanation: MPCDecisionPhysicalExplanation

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, MPCDecisionExplanationInput):
            raise TypeError("source_input must be an MPCDecisionExplanationInput")
        if isinstance(self.selected_step_index, bool) or not isinstance(
            self.selected_step_index, int
        ):
            raise TypeError("selected_step_index must be an integer")
        if self.selected_step_index < 0:
            raise ValueError("selected_step_index must be greater than or equal to 0")
        if not isinstance(self.decision, EMSDecision):
            raise TypeError("decision must be an EMSDecision")
        if not isinstance(self.candidate_action, DecisionIntent):
            raise TypeError("candidate_action must be a DecisionIntent")
        if not isinstance(self.final_action, DecisionIntent):
            raise TypeError("final_action must be a DecisionIntent")
        if not isinstance(self.revision_applied, bool):
            raise TypeError("revision_applied must be a bool")
        if not isinstance(self.physical_explanation, MPCDecisionPhysicalExplanation):
            raise TypeError(
                "physical_explanation must be an MPCDecisionPhysicalExplanation"
            )
        physical = self.physical_explanation
        if self.candidate_action is not physical.candidate_step.intent:
            raise ValueError("candidate action must preserve exact candidate intent")
        if (
            self.candidate_requested_power_kw
            != physical.candidate_step.requested_power_kw
        ):
            raise ValueError("candidate power must preserve exact candidate step power")
        if self.final_action is not physical.final_step.intent:
            raise ValueError("final action must preserve exact final intent")
        if self.final_requested_power_kw != physical.final_step.requested_power_kw:
            raise ValueError("final power must preserve exact final step power")
        expected_revision = (
            self.candidate_action.action != self.final_action.action
            or self.candidate_requested_power_kw != self.final_requested_power_kw
        )
        if self.revision_applied is not expected_revision:
            raise ValueError("revision_applied must reflect candidate-to-final change")
        cycle_result = self.source_input.cycle_result
        if self.decision is not cycle_result.decision:
            raise ValueError("decision must preserve exact cycle decision identity")
        if self.selected_step_index >= len(cycle_result.control_plan.steps):
            raise ValueError("selected_step_index must reference a plan step")


class MPCDecisionExplanationBoundary(ABC):
    """Define stateless read-only explanation of one completed physical cycle."""

    __slots__ = ()

    @abstractmethod
    def explain(
        self, explanation_input: MPCDecisionExplanationInput
    ) -> MPCDecisionExplanation:
        """Organize existing evidence for the selected current action only."""
        raise NotImplementedError


class DeterministicMPCDecisionExplanationBuilder(MPCDecisionExplanationBoundary):
    """Read an exact provenance graph without invoking any domain behavior."""

    __slots__ = ()

    def explain(
        self, explanation_input: MPCDecisionExplanationInput
    ) -> MPCDecisionExplanation:
        if not isinstance(explanation_input, MPCDecisionExplanationInput):
            raise TypeError("explanation_input must be an MPCDecisionExplanationInput")
        result = explanation_input.cycle_result
        selected_index = self._selected_plan_index(result)
        output = result.optimization_output
        candidate_step = output.candidate_output.solution.steps[selected_index]
        final_step = output.final_output.solution.steps[selected_index]
        revision_step = output.revision.steps[selected_index]
        self._validate_mapping(
            result, selected_index, candidate_step, final_step, revision_step
        )

        candidate_projection_step = output.candidate_projection.steps[selected_index]
        final_projection_step = output.final_projection.steps[selected_index]
        soc_kinds = tuple(
            violation.kind
            for violation in output.candidate_soc_evaluation.violations
            if violation.step_index == selected_index
        )
        power_kinds = tuple(
            violation.kind
            for violation in output.candidate_power_evaluation.violations
            if violation.step_index == selected_index
        )
        model = result.battery_input.battery_model
        physical = MPCDecisionPhysicalExplanation(
            candidate_step,
            final_step,
            revision_step,
            revision_step.reasons,
            soc_kinds,
            power_kinds,
            output.candidate_constraint_evaluation.feasible,
            output.final_soc_evaluation.feasible,
            output.final_power_evaluation.feasible,
            output.final_constraint_evaluation.feasible,
            candidate_projection_step.starting_soc_fraction,
            candidate_projection_step.ending_soc_fraction,
            final_projection_step.starting_soc_fraction,
            final_projection_step.ending_soc_fraction,
            model.min_soc_fraction,
            model.max_soc_fraction,
            model.max_charge_power_kw,
            model.max_discharge_power_kw,
        )
        return MPCDecisionExplanation(
            explanation_input,
            selected_index,
            result.decision,
            candidate_step.intent,
            candidate_step.requested_power_kw,
            final_step.intent,
            final_step.requested_power_kw,
            candidate_step.intent.action != final_step.intent.action
            or candidate_step.requested_power_kw != final_step.requested_power_kw,
            physical,
        )

    @staticmethod
    def _selected_plan_index(result: PhysicallyAwareMPCCycleResult) -> int:
        selected_step = result.current_action.selected_step
        for index, plan_step in enumerate(result.control_plan.steps):
            if plan_step is selected_step:
                return index
        raise ValueError("current action must reference an exact control plan step")

    @staticmethod
    def _validate_mapping(
        result: PhysicallyAwareMPCCycleResult,
        selected_index: int,
        candidate_step: OptimizationSolutionStep,
        final_step: OptimizationSolutionStep,
        revision_step: BatterySolutionRevisionStep,
    ) -> None:
        selected_plan_step = result.current_action.selected_step
        if revision_step.revised_step is not final_step:
            raise ValueError("revision step must preserve exact selected final step")
        if revision_step.source_candidate_step is not candidate_step:
            raise ValueError(
                "revision step must preserve exact selected candidate step"
            )
        if result.decision.requested_power_kw != selected_plan_step.requested_power_kw:
            raise ValueError("decision power must equal selected plan step power")
        if result.decision.intent is not selected_plan_step.intent:
            raise ValueError("decision intent must preserve exact selected plan intent")
        if final_step.intent is not selected_plan_step.intent:
            raise ValueError("final step must preserve exact selected plan intent")
        if final_step.requested_power_kw != selected_plan_step.requested_power_kw:
            raise ValueError("final step power must equal selected plan step power")
        if revision_step.step_index != selected_index:
            raise ValueError("revision step must preserve selected plan index")
