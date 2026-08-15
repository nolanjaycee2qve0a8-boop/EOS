"""Pure realized import-cost evidence.

This module multiplies caller-supplied realized import energy by one explicit
import tariff. It does not inspect grid signs, traces, tariff profiles,
forecasts, plans, decisions, control, or simulation artifacts.
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
class ImportCostInput:
    """Caller-owned realized import energy and one explicit import tariff.

    ``realized_import_energy_kwh`` is already a non-negative realized scalar.
    This contract neither derives it from grid-power signs nor selects a tariff
    from a schedule, market, tariff profile, or forecast.
    """

    realized_import_energy_kwh: float
    import_tariff_per_kwh: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "realized_import_energy_kwh",
            _require_non_negative_finite(
                self.realized_import_energy_kwh,
                "realized_import_energy_kwh",
            ),
        )
        object.__setattr__(
            self,
            "import_tariff_per_kwh",
            _require_non_negative_finite(
                self.import_tariff_per_kwh,
                "import_tariff_per_kwh",
            ),
        )


@dataclass(frozen=True, slots=True)
class ImportCostEvidence:
    """Realized import-cost evidence from supplied energy and tariff only."""

    source_input: ImportCostInput
    realized_import_energy_kwh: float
    import_tariff_per_kwh: float
    realized_import_cost: float

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, ImportCostInput):
            raise TypeError("source_input must be an ImportCostInput")
        for field_name in (
            "realized_import_energy_kwh",
            "import_tariff_per_kwh",
            "realized_import_cost",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_non_negative_finite(getattr(self, field_name), field_name),
            )
        if (
            self.realized_import_energy_kwh
            != self.source_input.realized_import_energy_kwh
            or self.import_tariff_per_kwh != self.source_input.import_tariff_per_kwh
        ):
            raise ValueError("import terms must preserve exact input semantics")
        if self.realized_import_cost != (
            self.realized_import_energy_kwh * self.import_tariff_per_kwh
        ):
            raise ValueError(
                "realized_import_cost must equal import energy times import tariff"
            )


class ImportCostBoundary(ABC):
    """Define a stateless realized import-cost evidence seam."""

    __slots__ = ()

    @abstractmethod
    def calculate(self, cost_input: ImportCostInput) -> ImportCostEvidence:
        """Multiply supplied realized energy and tariff only."""
        raise NotImplementedError


class DeterministicImportCostCalculator(ImportCostBoundary):
    """Apply the frozen realized-import-energy times tariff formula."""

    __slots__ = ()

    def calculate(self, cost_input: ImportCostInput) -> ImportCostEvidence:
        if not isinstance(cost_input, ImportCostInput):
            raise TypeError("cost_input must be an ImportCostInput")
        return ImportCostEvidence(
            cost_input,
            cost_input.realized_import_energy_kwh,
            cost_input.import_tariff_per_kwh,
            cost_input.realized_import_energy_kwh * cost_input.import_tariff_per_kwh,
        )
