"""Pure terminal-value-adjusted realized import-cost evidence.

This module consumes caller-supplied realized import cost and exact TASK-162
terminal-energy-value evidence. It neither reconstructs either source nor
inspects grids, tariffs, forecasts, battery state, candidates, or control.
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
class EconomicOutcomeInput:
    """Caller-owned realized import expense and already-valued terminal evidence.

    ``realized_import_cost`` is an already-reduced non-negative expense over a
    caller-defined horizon. This contract intentionally has no tariff profile,
    grid trace, forecast, or battery state from which that cost could be
    recalculated.
    """

    realized_import_cost: float
    terminal_energy_value_evidence: TerminalEnergyValueEvidence

    def __post_init__(self) -> None:
        if not isinstance(
            self.terminal_energy_value_evidence,
            TerminalEnergyValueEvidence,
        ):
            raise TypeError(
                "terminal_energy_value_evidence must be a TerminalEnergyValueEvidence"
            )
        object.__setattr__(
            self,
            "realized_import_cost",
            _require_non_negative_finite(
                self.realized_import_cost,
                "realized_import_cost",
            ),
        )


@dataclass(frozen=True, slots=True)
class EconomicOutcomeEvidence:
    """Limited accounting evidence: realized import cost less terminal credit.

    A lower ``net_economic_cost`` is preferable only under this narrow basis.
    A negative net cost is valid when the credited terminal energy value exceeds
    realized import expense; it is not cash profit. Export revenue, degradation,
    auxiliary use, fixed charges, taxes, uncertainty, and other opportunity or
    capital costs remain outside this contract.
    """

    source_input: EconomicOutcomeInput
    realized_import_cost: float
    terminal_energy_value_evidence: TerminalEnergyValueEvidence
    terminal_energy_value: float
    net_economic_cost: float
    terminal_value_credit_applied: bool

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, EconomicOutcomeInput):
            raise TypeError("source_input must be an EconomicOutcomeInput")
        if (
            self.terminal_energy_value_evidence
            is not self.source_input.terminal_energy_value_evidence
        ):
            raise ValueError(
                "terminal_energy_value_evidence must preserve exact source identity"
            )
        if not isinstance(self.terminal_value_credit_applied, bool):
            raise TypeError("terminal_value_credit_applied must be a bool")
        realized_import_cost = _require_non_negative_finite(
            self.realized_import_cost,
            "realized_import_cost",
        )
        terminal_energy_value = _require_non_negative_finite(
            self.terminal_energy_value,
            "terminal_energy_value",
        )
        if realized_import_cost != self.source_input.realized_import_cost:
            raise ValueError("realized_import_cost must preserve exact input semantics")
        expected_terminal_value = (
            self.terminal_energy_value_evidence.terminal_energy_value
        )
        if terminal_energy_value != expected_terminal_value:
            raise ValueError(
                "terminal_energy_value must preserve supplied terminal evidence"
            )
        if isinstance(self.net_economic_cost, bool) or not isinstance(
            self.net_economic_cost,
            int | float,
        ):
            raise TypeError("net_economic_cost must be a number")
        net_economic_cost = float(self.net_economic_cost)
        if not isfinite(net_economic_cost):
            raise ValueError("net_economic_cost must be finite")
        if net_economic_cost != realized_import_cost - terminal_energy_value:
            raise ValueError(
                "net_economic_cost must equal realized import cost minus terminal value"
            )
        if self.terminal_value_credit_applied != (terminal_energy_value > 0.0):
            raise ValueError(
                "terminal_value_credit_applied must reflect terminal value evidence"
            )
        object.__setattr__(self, "realized_import_cost", realized_import_cost)
        object.__setattr__(self, "terminal_energy_value", terminal_energy_value)
        object.__setattr__(self, "net_economic_cost", net_economic_cost)


class EconomicOutcomeBoundary(ABC):
    """Define a stateless terminal-value-adjusted economic evidence seam."""

    __slots__ = ()

    @abstractmethod
    def calculate(self, outcome_input: EconomicOutcomeInput) -> EconomicOutcomeEvidence:
        """Combine supplied evidence only; never recalculate either source."""
        raise NotImplementedError


class DeterministicEconomicOutcomeCalculator(EconomicOutcomeBoundary):
    """Apply the frozen limited-accounting terminal-value credit formula."""

    __slots__ = ()

    def calculate(self, outcome_input: EconomicOutcomeInput) -> EconomicOutcomeEvidence:
        if not isinstance(outcome_input, EconomicOutcomeInput):
            raise TypeError("outcome_input must be an EconomicOutcomeInput")
        terminal_evidence = outcome_input.terminal_energy_value_evidence
        terminal_value = terminal_evidence.terminal_energy_value
        return EconomicOutcomeEvidence(
            outcome_input,
            outcome_input.realized_import_cost,
            terminal_evidence,
            terminal_value,
            outcome_input.realized_import_cost - terminal_value,
            terminal_value > 0.0,
        )
