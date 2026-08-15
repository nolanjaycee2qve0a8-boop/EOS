"""Pure realized export-revenue evidence.

This module multiplies caller-supplied realized export energy by one explicit
realized or average export tariff. It does not inspect grid signs, traces,
tariffs over time, forecasts, candidates, control, or simulation artifacts.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import isfinite


def _require_non_negative_finite(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized) or normalized < 0.0:
        raise ValueError(f"{field_name} must be finite and non-negative")
    return normalized


@dataclass(frozen=True, slots=True)
class ExportRevenueInput:
    """Caller-owned realized export energy and one explicit export tariff.

    ``realized_export_energy_kwh`` is already a non-negative realized scalar.
    This contract neither derives export energy from grid power nor selects a
    tariff from a profile, market, or forecast.
    """

    realized_export_energy_kwh: float
    export_tariff_per_kwh: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "realized_export_energy_kwh",
            _require_non_negative_finite(
                self.realized_export_energy_kwh,
                "realized_export_energy_kwh",
            ),
        )
        object.__setattr__(
            self,
            "export_tariff_per_kwh",
            _require_non_negative_finite(
                self.export_tariff_per_kwh,
                "export_tariff_per_kwh",
            ),
        )


@dataclass(frozen=True, slots=True)
class ExportRevenueEvidence:
    """Realized export revenue evidence from supplied energy and tariff only."""

    source_input: ExportRevenueInput
    realized_export_energy_kwh: float
    export_tariff_per_kwh: float
    realized_export_revenue: float

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, ExportRevenueInput):
            raise TypeError("source_input must be an ExportRevenueInput")
        for field_name in (
            "realized_export_energy_kwh",
            "export_tariff_per_kwh",
            "realized_export_revenue",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_non_negative_finite(getattr(self, field_name), field_name),
            )
        if (
            self.realized_export_energy_kwh
            != self.source_input.realized_export_energy_kwh
            or self.export_tariff_per_kwh != self.source_input.export_tariff_per_kwh
        ):
            raise ValueError("export terms must preserve exact input semantics")
        if (
            self.realized_export_revenue
            != self.realized_export_energy_kwh * self.export_tariff_per_kwh
        ):
            raise ValueError(
                "realized_export_revenue must equal export energy times export tariff"
            )


class ExportRevenueBoundary(ABC):
    """Define a stateless realized export-revenue evidence seam."""

    __slots__ = ()

    @abstractmethod
    def calculate(self, revenue_input: ExportRevenueInput) -> ExportRevenueEvidence:
        """Multiply supplied realized energy and tariff only."""
        raise NotImplementedError


class DeterministicExportRevenueCalculator(ExportRevenueBoundary):
    """Apply the frozen realized-export-energy times tariff formula."""

    __slots__ = ()

    def calculate(self, revenue_input: ExportRevenueInput) -> ExportRevenueEvidence:
        if not isinstance(revenue_input, ExportRevenueInput):
            raise TypeError("revenue_input must be an ExportRevenueInput")
        return ExportRevenueEvidence(
            revenue_input,
            revenue_input.realized_export_energy_kwh,
            revenue_input.export_tariff_per_kwh,
            revenue_input.realized_export_energy_kwh
            * revenue_input.export_tariff_per_kwh,
        )
