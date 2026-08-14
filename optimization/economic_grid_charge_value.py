"""Pure composition of current headroom allowance and economic shift evidence.

This module consumes already-computed TASK-148 reservation evidence and
TASK-155 economic evidence.  It does not recalculate schedules, reservations,
or economics, and it does not modify candidates or control execution.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import isfinite

from optimization.economic_planning import (
    EconomicPlanningEvidence,
    EconomicPlanningStepEvidence,
    EconomicShiftClassification,
)
from optimization.multi_opportunity_grid_charge_reservation import (
    MultiOpportunityGridChargeReservationResult,
)


def _require_non_negative_index(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an int")
    if value < 0:
        raise ValueError(f"{field_name} must be greater than or equal to 0")
    return value


def _require_non_negative_finite(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized) or normalized < 0.0:
        raise ValueError(f"{field_name} must be finite and non-negative")
    return normalized


@dataclass(frozen=True, slots=True)
class EconomicGridChargeValueInput:
    """Compose exact completed reservation and economic evidence for one step.

    The input carries no standalone horizon, battery model, SOC, candidate, or
    simulator state.  Those facts remain navigable from the exact evidence
    objects supplied by the caller.
    """

    reservation_result: MultiOpportunityGridChargeReservationResult
    economic_planning_evidence: EconomicPlanningEvidence
    current_source_index: int

    def __post_init__(self) -> None:
        if not isinstance(
            self.reservation_result,
            MultiOpportunityGridChargeReservationResult,
        ):
            raise TypeError(
                "reservation_result must be a "
                "MultiOpportunityGridChargeReservationResult"
            )
        if not isinstance(self.economic_planning_evidence, EconomicPlanningEvidence):
            raise TypeError(
                "economic_planning_evidence must be an EconomicPlanningEvidence"
            )
        object.__setattr__(
            self,
            "current_source_index",
            _require_non_negative_index(
                self.current_source_index,
                "current_source_index",
            ),
        )
        if self.current_source_index >= len(self.economic_planning_evidence.steps):
            raise ValueError(
                "current_source_index must identify an economic evidence step"
            )
        reservation_input = self.reservation_result.source_input
        reservation_horizon = (
            reservation_input.headroom_schedule.source_input.forecast_horizon
        )
        economic_input = self.economic_planning_evidence.source_input
        if reservation_horizon is not economic_input.forecast_horizon:
            raise ValueError(
                "reservation and economic evidence must preserve exact forecast "
                "identity"
            )
        if reservation_input.battery_model is not economic_input.battery_model:
            raise ValueError(
                "reservation and economic evidence must preserve exact battery model "
                "identity"
            )


@dataclass(frozen=True, slots=True)
class EconomicGridChargeValueResult:
    """Read-only current grid-charge value evidence.

    A positive gross TASK-155 margin preserves the completed headroom allowance.
    BREAK_EVEN, NEGATIVE, and UNAVAILABLE all map to zero supported power.  The
    BREAK_EVEN mapping is deliberately conservative because gross margin omits
    degradation, uncertainty, auxiliary losses, and opportunity cost.  This is
    evidence semantics only, never a final battery decision.
    """

    source_input: EconomicGridChargeValueInput
    reservation_result: MultiOpportunityGridChargeReservationResult
    economic_step_evidence: EconomicPlanningStepEvidence
    requested_grid_charge_power_kw: float
    headroom_allowed_grid_charge_power_kw: float
    economically_supported_grid_charge_power_kw: float
    economic_classification: EconomicShiftClassification
    economic_support_applied: bool

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, EconomicGridChargeValueInput):
            raise TypeError("source_input must be an EconomicGridChargeValueInput")
        if self.reservation_result is not self.source_input.reservation_result:
            raise ValueError(
                "reservation_result must preserve exact source input identity"
            )
        selected_step = self.source_input.economic_planning_evidence.steps[
            self.source_input.current_source_index
        ]
        if self.economic_step_evidence is not selected_step:
            raise ValueError(
                "economic_step_evidence must preserve exact selected identity"
            )
        if not isinstance(self.economic_classification, EconomicShiftClassification):
            raise TypeError(
                "economic_classification must be an EconomicShiftClassification"
            )
        if not isinstance(self.economic_support_applied, bool):
            raise TypeError("economic_support_applied must be a bool")
        for field_name in (
            "requested_grid_charge_power_kw",
            "headroom_allowed_grid_charge_power_kw",
            "economically_supported_grid_charge_power_kw",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_non_negative_finite(getattr(self, field_name), field_name),
            )
        self._validate_semantics()

    def _validate_semantics(self) -> None:
        reservation = self.reservation_result
        expected_supported = (
            reservation.allowed_grid_charge_power_kw
            if self.economic_step_evidence.classification
            is EconomicShiftClassification.POSITIVE
            else 0.0
        )
        expected = (
            reservation.requested_grid_charge_power_kw,
            reservation.allowed_grid_charge_power_kw,
            expected_supported,
            self.economic_step_evidence.classification,
            expected_supported < reservation.allowed_grid_charge_power_kw,
        )
        actual = (
            self.requested_grid_charge_power_kw,
            self.headroom_allowed_grid_charge_power_kw,
            self.economically_supported_grid_charge_power_kw,
            self.economic_classification,
            self.economic_support_applied,
        )
        if actual != expected:
            raise ValueError(
                "result must preserve exact reservation and economic evidence"
            )


class EconomicGridChargeValueBoundary(ABC):
    """Define a stateless boundary combining completed physical and value evidence."""

    __slots__ = ()

    @abstractmethod
    def calculate(
        self,
        value_input: EconomicGridChargeValueInput,
    ) -> EconomicGridChargeValueResult:
        """Combine evidence only; never calculate sources or modify a candidate."""
        raise NotImplementedError


class DeterministicEconomicGridChargeValueCalculator(EconomicGridChargeValueBoundary):
    """Gate completed headroom allowance with the exact selected gross margin."""

    __slots__ = ()

    def calculate(
        self,
        value_input: EconomicGridChargeValueInput,
    ) -> EconomicGridChargeValueResult:
        if not isinstance(value_input, EconomicGridChargeValueInput):
            raise TypeError("value_input must be an EconomicGridChargeValueInput")
        reservation = value_input.reservation_result
        economic_step = value_input.economic_planning_evidence.steps[
            value_input.current_source_index
        ]
        supported = (
            reservation.allowed_grid_charge_power_kw
            if economic_step.classification is EconomicShiftClassification.POSITIVE
            else 0.0
        )
        return EconomicGridChargeValueResult(
            value_input,
            reservation,
            economic_step,
            reservation.requested_grid_charge_power_kw,
            reservation.allowed_grid_charge_power_kw,
            supported,
            economic_step.classification,
            supported < reservation.allowed_grid_charge_power_kw,
        )
