"""Read-only per-decision journal records for explained physical MPC cycles."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from decision_formation import DecisionIntent
from ems_strategy.descriptor import EMSStrategyDescriptor
from ems_strategy.mpc_decision_explanation import MPCDecisionExplanation
from ems_strategy.mpc_decision_explanation_formatter import (
    FormattedMPCDecisionExplanation,
)
from ems_strategy.mpc_physically_aware import PhysicallyAwareMPCCycleResult

BatterySolutionRevisionReason = Literal[
    "charge_power_limit",
    "discharge_power_limit",
    "max_soc_limit",
    "min_soc_limit",
]
BatterySOCConstraintViolationKind = Literal["below_min_soc", "above_max_soc"]
BatteryPowerConstraintViolationKind = Literal[
    "charge_power_above_max",
    "discharge_power_above_max",
]


@dataclass(frozen=True, slots=True)
class ExplainableMPCDecisionJournalRecordInput:
    """Compose exact completed-cycle and explanation artifacts for one record."""

    cycle_result: PhysicallyAwareMPCCycleResult
    explanation: MPCDecisionExplanation
    formatted_explanation: FormattedMPCDecisionExplanation

    def __post_init__(self) -> None:
        if not isinstance(self.cycle_result, PhysicallyAwareMPCCycleResult):
            raise TypeError("cycle_result must be a PhysicallyAwareMPCCycleResult")
        if not isinstance(self.explanation, MPCDecisionExplanation):
            raise TypeError("explanation must be an MPCDecisionExplanation")
        if not isinstance(self.formatted_explanation, FormattedMPCDecisionExplanation):
            raise TypeError(
                "formatted_explanation must be a FormattedMPCDecisionExplanation"
            )
        if self.explanation.source_input.cycle_result is not self.cycle_result:
            raise ValueError("explanation must preserve exact cycle result identity")
        if self.formatted_explanation.source_input.explanation is not self.explanation:
            raise ValueError(
                "formatted explanation must preserve exact explanation identity"
            )


@dataclass(frozen=True, slots=True)
class ExplainableMPCDecisionJournalRecord:
    """Retain stable raw and formatted evidence for one exact MPC decision."""

    source_input: ExplainableMPCDecisionJournalRecordInput
    timestamp: datetime
    strategy: EMSStrategyDescriptor
    final_action: DecisionIntent
    final_requested_power_kw: float
    candidate_action: DecisionIntent
    candidate_requested_power_kw: float
    revision_applied: bool
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
    formatted_text: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, ExplainableMPCDecisionJournalRecordInput):
            raise TypeError(
                "source_input must be an ExplainableMPCDecisionJournalRecordInput"
            )
        input_ = self.source_input
        explanation = input_.explanation
        physical = explanation.physical_explanation
        source_context = input_.cycle_result.source_input.cycle_input.context
        if self.timestamp is not source_context.source_context.timestamp:
            raise ValueError("timestamp must preserve exact decision context timestamp")
        if (
            self.strategy
            is not input_.cycle_result.source_input.cycle_input.source_strategy
        ):
            raise ValueError("strategy must preserve exact cycle strategy identity")
        if self.final_action is not explanation.final_action:
            raise ValueError("final_action must preserve exact explanation identity")
        if self.candidate_action is not explanation.candidate_action:
            raise ValueError(
                "candidate_action must preserve exact explanation identity"
            )
        if self.final_requested_power_kw != explanation.final_requested_power_kw:
            raise ValueError("final power must preserve exact explanation value")
        if (
            self.candidate_requested_power_kw
            != explanation.candidate_requested_power_kw
        ):
            raise ValueError("candidate power must preserve exact explanation value")
        if self.revision_applied is not explanation.revision_applied:
            raise ValueError("revision_applied must preserve exact explanation value")
        if self.revision_reasons is not physical.revision_reasons:
            raise ValueError("revision_reasons must preserve exact explanation tuple")
        if (
            self.candidate_soc_violation_kinds
            is not physical.candidate_soc_violation_kinds
        ):
            raise ValueError(
                "SOC violation kinds must preserve exact explanation tuple"
            )
        if (
            self.candidate_power_violation_kinds
            is not physical.candidate_power_violation_kinds
        ):
            raise ValueError(
                "power violation kinds must preserve exact explanation tuple"
            )
        for field_name in (
            "candidate_battery_horizon_feasible",
            "final_soc_feasible",
            "final_power_feasible",
            "final_battery_horizon_feasible",
        ):
            if getattr(self, field_name) is not getattr(physical, field_name):
                raise ValueError(f"{field_name} must preserve exact explanation value")
        for field_name in (
            "candidate_starting_soc_fraction",
            "candidate_ending_soc_fraction",
            "final_starting_soc_fraction",
            "final_ending_soc_fraction",
            "min_soc_fraction",
            "max_soc_fraction",
            "max_charge_power_kw",
            "max_discharge_power_kw",
        ):
            if getattr(self, field_name) != getattr(physical, field_name):
                raise ValueError(f"{field_name} must preserve exact explanation value")
        if self.formatted_text != input_.formatted_explanation.text:
            raise ValueError(
                "formatted_text must preserve exact formatted explanation text"
            )


class ExplainableMPCDecisionJournalRecordBoundary(ABC):
    """Define stateless construction of one explainable decision record."""

    __slots__ = ()

    @abstractmethod
    def build(
        self,
        record_input: ExplainableMPCDecisionJournalRecordInput,
    ) -> ExplainableMPCDecisionJournalRecord:
        """Read supplied evidence only; do not execute or persist it."""
        raise NotImplementedError


class DeterministicExplainableMPCDecisionJournalRecordBuilder(
    ExplainableMPCDecisionJournalRecordBoundary
):
    """Build one record directly from existing exact explanation artifacts."""

    __slots__ = ()

    def build(
        self,
        record_input: ExplainableMPCDecisionJournalRecordInput,
    ) -> ExplainableMPCDecisionJournalRecord:
        if not isinstance(record_input, ExplainableMPCDecisionJournalRecordInput):
            raise TypeError(
                "record_input must be an ExplainableMPCDecisionJournalRecordInput"
            )
        explanation = record_input.explanation
        physical = explanation.physical_explanation
        cycle = record_input.cycle_result
        return ExplainableMPCDecisionJournalRecord(
            record_input,
            cycle.source_input.cycle_input.context.source_context.timestamp,
            cycle.source_input.cycle_input.source_strategy,
            explanation.final_action,
            explanation.final_requested_power_kw,
            explanation.candidate_action,
            explanation.candidate_requested_power_kw,
            explanation.revision_applied,
            physical.revision_reasons,
            physical.candidate_soc_violation_kinds,
            physical.candidate_power_violation_kinds,
            physical.candidate_battery_horizon_feasible,
            physical.final_soc_feasible,
            physical.final_power_feasible,
            physical.final_battery_horizon_feasible,
            physical.candidate_starting_soc_fraction,
            physical.candidate_ending_soc_fraction,
            physical.final_starting_soc_fraction,
            physical.final_ending_soc_fraction,
            physical.min_soc_fraction,
            physical.max_soc_fraction,
            physical.max_charge_power_kw,
            physical.max_discharge_power_kw,
            record_input.formatted_explanation.text,
        )
