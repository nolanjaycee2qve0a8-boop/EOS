"""Pure assigned value evidence for known terminal battery stored energy.

The caller supplies the valuation import price.  This module does not inspect
forecasts, select a tariff, combine value with realized cost, or modify any
candidate, optimization, MPC, feasibility, actuation, or simulation path.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import isfinite

from optimization.battery_planning import BatteryOptimizationModel


def _require_finite_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    return normalized


def _require_non_negative_finite(value: object, field_name: str) -> float:
    normalized = _require_finite_number(value, field_name)
    if normalized < 0.0:
        raise ValueError(f"{field_name} must be non-negative")
    return normalized


@dataclass(frozen=True, slots=True)
class TerminalEnergyValueInput:
    """Caller-owned terminal state, planning model, and valuation assumption.

    ``terminal_soc`` must lie within the exact battery model's physical planning
    interval. ``valuation_import_price`` is a non-negative caller-supplied
    currency-per-kWh assumption; this contract deliberately does not select it.
    """

    terminal_soc: float
    battery_model: BatteryOptimizationModel
    valuation_import_price: float

    def __post_init__(self) -> None:
        if not isinstance(self.battery_model, BatteryOptimizationModel):
            raise TypeError("battery_model must be a BatteryOptimizationModel")
        terminal_soc = _require_finite_number(self.terminal_soc, "terminal_soc")
        if not (
            self.battery_model.min_soc_fraction
            <= terminal_soc
            <= self.battery_model.max_soc_fraction
        ):
            raise ValueError("terminal_soc must be within the battery model SOC range")
        object.__setattr__(self, "terminal_soc", terminal_soc)
        object.__setattr__(
            self,
            "valuation_import_price",
            _require_non_negative_finite(
                self.valuation_import_price,
                "valuation_import_price",
            ),
        )


@dataclass(frozen=True, slots=True)
class TerminalEnergyValueEvidence:
    """Assigned avoided-import value of terminal usable stored energy.

    Stored energy is measured above ``battery_model.min_soc_fraction``.  It is
    converted to load-side deliverable energy with discharge efficiency, then
    valued with the caller's supplied import price.  The result is neither
    realized revenue/cost saving nor a profit or optimization decision.
    """

    source_input: TerminalEnergyValueInput
    usable_soc_fraction: float
    usable_terminal_stored_energy_kwh: float
    discharge_efficiency: float
    deliverable_terminal_energy_kwh: float
    valuation_import_price: float
    value_per_stored_kwh: float
    terminal_energy_value: float

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, TerminalEnergyValueInput):
            raise TypeError("source_input must be a TerminalEnergyValueInput")
        for field_name in (
            "usable_soc_fraction",
            "usable_terminal_stored_energy_kwh",
            "deliverable_terminal_energy_kwh",
            "valuation_import_price",
            "value_per_stored_kwh",
            "terminal_energy_value",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_non_negative_finite(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self,
            "discharge_efficiency",
            _require_non_negative_finite(
                self.discharge_efficiency,
                "discharge_efficiency",
            ),
        )
        if not 0.0 < self.discharge_efficiency <= 1.0:
            raise ValueError(
                "discharge_efficiency must be greater than 0 and at most 1"
            )
        self._validate_semantics()

    def _validate_semantics(self) -> None:
        model = self.source_input.battery_model
        usable_soc = max(self.source_input.terminal_soc - model.min_soc_fraction, 0.0)
        stored_energy = usable_soc * model.usable_capacity_kwh
        deliverable_energy = stored_energy * model.discharge_efficiency
        value_per_stored = (
            model.discharge_efficiency * self.source_input.valuation_import_price
        )
        terminal_value = deliverable_energy * self.source_input.valuation_import_price
        expected = (
            usable_soc,
            stored_energy,
            model.discharge_efficiency,
            deliverable_energy,
            self.source_input.valuation_import_price,
            value_per_stored,
            terminal_value,
        )
        actual = (
            self.usable_soc_fraction,
            self.usable_terminal_stored_energy_kwh,
            self.discharge_efficiency,
            self.deliverable_terminal_energy_kwh,
            self.valuation_import_price,
            self.value_per_stored_kwh,
            self.terminal_energy_value,
        )
        if actual != expected:
            raise ValueError(
                "terminal value evidence must preserve exact input semantics"
            )


class TerminalEnergyValueBoundary(ABC):
    """Define a stateless terminal stored-energy valuation seam."""

    __slots__ = ()

    @abstractmethod
    def calculate(
        self,
        value_input: TerminalEnergyValueInput,
    ) -> TerminalEnergyValueEvidence:
        """Return evidence only; never select a price or aggregate economics."""
        raise NotImplementedError


class DeterministicTerminalEnergyValueCalculator(TerminalEnergyValueBoundary):
    """Apply the explicit stored-energy, efficiency, and valuation-price formula."""

    __slots__ = ()

    def calculate(
        self,
        value_input: TerminalEnergyValueInput,
    ) -> TerminalEnergyValueEvidence:
        if not isinstance(value_input, TerminalEnergyValueInput):
            raise TypeError("value_input must be a TerminalEnergyValueInput")
        model = value_input.battery_model
        usable_soc = max(value_input.terminal_soc - model.min_soc_fraction, 0.0)
        stored_energy = usable_soc * model.usable_capacity_kwh
        deliverable_energy = stored_energy * model.discharge_efficiency
        value_per_stored = (
            model.discharge_efficiency * value_input.valuation_import_price
        )
        terminal_value = deliverable_energy * value_input.valuation_import_price
        return TerminalEnergyValueEvidence(
            value_input,
            usable_soc,
            stored_energy,
            model.discharge_efficiency,
            deliverable_energy,
            value_input.valuation_import_price,
            value_per_stored,
            terminal_value,
        )
