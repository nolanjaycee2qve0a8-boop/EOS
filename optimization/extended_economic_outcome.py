"""Pure extended economic accounting evidence.

This module aggregates caller-supplied realized import expense, export revenue,
battery degradation cost, and exact TASK-162 terminal-value evidence. It does
not inspect or recalculate grids, tariffs, forecasts, battery throughput,
candidates, decisions, control, or simulation artifacts.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import isfinite

from optimization.terminal_energy_value import TerminalEnergyValueEvidence


def _require_non_negative_finite(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized) or normalized < 0.0:
        raise ValueError(f"{field_name} must be finite and non-negative")
    return normalized


@dataclass(frozen=True, slots=True)
class ExtendedEconomicOutcomeInput:
    """Caller-owned accounting components and already-valued terminal evidence.

    All scalar components are already-reduced non-negative costs or revenue for
    a caller-defined horizon. The contract has no traces or tariff inputs from
    which any component could be recalculated.
    """

    realized_import_cost: float
    realized_export_revenue: float
    battery_degradation_cost: float
    terminal_energy_value_evidence: TerminalEnergyValueEvidence

    def __post_init__(self) -> None:
        if not isinstance(
            self.terminal_energy_value_evidence,
            TerminalEnergyValueEvidence,
        ):
            raise TypeError(
                "terminal_energy_value_evidence must be a TerminalEnergyValueEvidence"
            )
        for field_name in (
            "realized_import_cost",
            "realized_export_revenue",
            "battery_degradation_cost",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_non_negative_finite(getattr(self, field_name), field_name),
            )


@dataclass(frozen=True, slots=True)
class ExtendedEconomicOutcomeEvidence:
    """Extended accounting evidence with export revenue and degradation terms.

    ``adjusted_net_economic_cost`` may be negative and is deliberately not
    clamped. It is limited accounting evidence, not realized cash profit.
    """

    source_input: ExtendedEconomicOutcomeInput
    realized_import_cost: float
    realized_export_revenue: float
    battery_degradation_cost: float
    terminal_energy_value_evidence: TerminalEnergyValueEvidence
    terminal_energy_value: float
    adjusted_net_economic_cost: float

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, ExtendedEconomicOutcomeInput):
            raise TypeError("source_input must be an ExtendedEconomicOutcomeInput")
        if (
            self.terminal_energy_value_evidence
            is not self.source_input.terminal_energy_value_evidence
        ):
            raise ValueError(
                "terminal_energy_value_evidence must preserve exact source identity"
            )
        for field_name in (
            "realized_import_cost",
            "realized_export_revenue",
            "battery_degradation_cost",
            "terminal_energy_value",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_non_negative_finite(getattr(self, field_name), field_name),
            )
        if (
            self.realized_import_cost != self.source_input.realized_import_cost
            or self.realized_export_revenue != self.source_input.realized_export_revenue
            or self.battery_degradation_cost
            != self.source_input.battery_degradation_cost
        ):
            raise ValueError(
                "accounting components must preserve exact input semantics"
            )
        if (
            self.terminal_energy_value
            != self.terminal_energy_value_evidence.terminal_energy_value
        ):
            raise ValueError(
                "terminal_energy_value must preserve supplied terminal evidence"
            )
        if isinstance(self.adjusted_net_economic_cost, bool) or not isinstance(
            self.adjusted_net_economic_cost,
            int | float,
        ):
            raise TypeError("adjusted_net_economic_cost must be a number")
        adjusted_net_economic_cost = float(self.adjusted_net_economic_cost)
        if not isfinite(adjusted_net_economic_cost):
            raise ValueError("adjusted_net_economic_cost must be finite")
        expected = (
            self.realized_import_cost
            - self.realized_export_revenue
            + self.battery_degradation_cost
            - self.terminal_energy_value
        )
        if adjusted_net_economic_cost != expected:
            raise ValueError(
                "adjusted_net_economic_cost must preserve supplied accounting semantics"
            )
        object.__setattr__(
            self,
            "adjusted_net_economic_cost",
            adjusted_net_economic_cost,
        )


class ExtendedEconomicOutcomeBoundary(ABC):
    """Define a stateless extended economic accounting evidence seam."""

    __slots__ = ()

    @abstractmethod
    def calculate(
        self,
        outcome_input: ExtendedEconomicOutcomeInput,
    ) -> ExtendedEconomicOutcomeEvidence:
        """Aggregate supplied evidence only; never recalculate any component."""
        raise NotImplementedError


class DeterministicExtendedEconomicOutcomeCalculator(ExtendedEconomicOutcomeBoundary):
    """Apply the frozen extended accounting formula to supplied evidence only."""

    __slots__ = ()

    def calculate(
        self,
        outcome_input: ExtendedEconomicOutcomeInput,
    ) -> ExtendedEconomicOutcomeEvidence:
        if not isinstance(outcome_input, ExtendedEconomicOutcomeInput):
            raise TypeError("outcome_input must be an ExtendedEconomicOutcomeInput")
        terminal_evidence = outcome_input.terminal_energy_value_evidence
        terminal_value = terminal_evidence.terminal_energy_value
        return ExtendedEconomicOutcomeEvidence(
            outcome_input,
            outcome_input.realized_import_cost,
            outcome_input.realized_export_revenue,
            outcome_input.battery_degradation_cost,
            terminal_evidence,
            terminal_value,
            outcome_input.realized_import_cost
            - outcome_input.realized_export_revenue
            + outcome_input.battery_degradation_cost
            - terminal_value,
        )
