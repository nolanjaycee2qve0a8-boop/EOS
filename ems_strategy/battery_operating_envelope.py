"""Battery operating envelope facts and abstract feasibility boundary."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import isfinite

from ems_strategy.decision import EMSDecision
from ems_strategy.provenance import DecisionProvenance


def _require_fraction(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized) or not 0 <= normalized <= 1:
        raise ValueError(f"{field_name} must be finite and between 0 and 1")
    return normalized


def _require_non_negative_power(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized) or normalized < 0:
        raise ValueError(f"{field_name} must be finite and non-negative")
    return normalized


@dataclass(frozen=True, slots=True)
class BatteryOperatingEnvelope:
    """Describe caller-supplied immutable Battery operating limits.

    SOC limits are raw unitless fractions in ``[0, 1]``. Power limits are
    finite non-negative raw kW magnitudes. This artifact contains facts only.
    """

    minimum_soc: float
    maximum_soc: float
    maximum_charge_power_kw: float
    maximum_discharge_power_kw: float

    def __post_init__(self) -> None:
        minimum_soc = _require_fraction(self.minimum_soc, "minimum_soc")
        maximum_soc = _require_fraction(self.maximum_soc, "maximum_soc")
        if minimum_soc > maximum_soc:
            raise ValueError("minimum_soc must be less than or equal to maximum_soc")
        object.__setattr__(self, "minimum_soc", minimum_soc)
        object.__setattr__(self, "maximum_soc", maximum_soc)
        object.__setattr__(
            self,
            "maximum_charge_power_kw",
            _require_non_negative_power(
                self.maximum_charge_power_kw,
                "maximum_charge_power_kw",
            ),
        )
        object.__setattr__(
            self,
            "maximum_discharge_power_kw",
            _require_non_negative_power(
                self.maximum_discharge_power_kw,
                "maximum_discharge_power_kw",
            ),
        )


@dataclass(frozen=True, slots=True)
class BatteryOperatingEnvelopeFeasibility:
    """Record feasibility against one exact Battery operating envelope."""

    source_decision: EMSDecision
    source_provenance: DecisionProvenance
    source_envelope: BatteryOperatingEnvelope
    is_feasible: bool

    def __post_init__(self) -> None:
        if not isinstance(self.source_decision, EMSDecision):
            raise TypeError("source_decision must be an EMSDecision")
        if not isinstance(self.source_provenance, DecisionProvenance):
            raise TypeError("source_provenance must be a DecisionProvenance")
        if self.source_provenance.decision is not self.source_decision:
            raise ValueError(
                "source_provenance must preserve exact source_decision identity"
            )
        if not isinstance(self.source_envelope, BatteryOperatingEnvelope):
            raise TypeError("source_envelope must be a BatteryOperatingEnvelope")
        if not isinstance(self.is_feasible, bool):
            raise TypeError("is_feasible must be a bool")


class BatteryOperatingEnvelopeBoundary(ABC):
    """Define stateless Battery operating-envelope feasibility evaluation."""

    __slots__ = ()

    def evaluate(
        self,
        decision: EMSDecision,
        *,
        provenance: DecisionProvenance,
        envelope: BatteryOperatingEnvelope,
    ) -> BatteryOperatingEnvelopeFeasibility:
        """Return one identity-preserving feasibility fact."""
        if not isinstance(decision, EMSDecision):
            raise TypeError("decision must be an EMSDecision")
        if not isinstance(provenance, DecisionProvenance):
            raise TypeError("provenance must be a DecisionProvenance")
        if provenance.decision is not decision:
            raise ValueError("provenance must preserve exact decision identity")
        if not isinstance(envelope, BatteryOperatingEnvelope):
            raise TypeError("envelope must be a BatteryOperatingEnvelope")

        result = self._evaluate(
            decision,
            provenance=provenance,
            envelope=envelope,
        )
        if not isinstance(result, BatteryOperatingEnvelopeFeasibility):
            raise TypeError(
                "evaluate must return a BatteryOperatingEnvelopeFeasibility"
            )
        if result.source_decision is not decision:
            raise ValueError("result must preserve exact source_decision identity")
        if result.source_provenance is not provenance:
            raise ValueError("result must preserve exact source_provenance identity")
        if result.source_envelope is not envelope:
            raise ValueError("result must preserve exact source_envelope identity")
        return result

    @abstractmethod
    def _evaluate(
        self,
        decision: EMSDecision,
        *,
        provenance: DecisionProvenance,
        envelope: BatteryOperatingEnvelope,
    ) -> BatteryOperatingEnvelopeFeasibility:
        """Represent feasibility without correction or retained state."""
        raise NotImplementedError
