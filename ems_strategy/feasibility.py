"""Immutable feasibility result and abstract evaluation boundary."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import isfinite

from decision_formation import DecisionIntent
from ems_strategy.decision import EMSDecision
from ems_strategy.provenance import DecisionProvenance


def _require_approved_power(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("approved_power_kw must be a number")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError("approved_power_kw must be finite")
    if normalized < 0:
        raise ValueError("approved_power_kw must be greater than or equal to 0")
    return normalized


@dataclass(frozen=True, slots=True)
class FeasibleDecision:
    """Represent one approved action without simulation or command meaning.

    ``approved_power_kw`` is a finite non-negative raw kW magnitude. Direction
    is expressed by ``approved_intent.action``. Feasibility may preserve the
    requested charge/discharge action or reduce it to idle, but it must not
    reverse the source strategy action.
    """

    source_decision: EMSDecision
    source_provenance: DecisionProvenance
    approved_intent: DecisionIntent
    approved_power_kw: float

    def __post_init__(self) -> None:
        if not isinstance(self.source_decision, EMSDecision):
            raise TypeError("source_decision must be an EMSDecision")
        if not isinstance(self.source_provenance, DecisionProvenance):
            raise TypeError("source_provenance must be a DecisionProvenance")
        if self.source_provenance.decision is not self.source_decision:
            raise ValueError(
                "source_provenance must preserve exact source_decision identity"
            )
        if not isinstance(self.approved_intent, DecisionIntent):
            raise TypeError("approved_intent must be a DecisionIntent")

        approved_power_kw = _require_approved_power(self.approved_power_kw)
        if self.approved_intent.action == "idle" and approved_power_kw != 0:
            raise ValueError(
                "idle approved_intent requires approved_power_kw equal to 0"
            )
        if self.approved_intent.action != "idle" and approved_power_kw == 0:
            raise ValueError(
                "charge and discharge approved_intents require approved_power_kw "
                "greater than 0"
            )

        source_action = self.source_decision.intent.action
        approved_action = self.approved_intent.action
        if approved_action not in (source_action, "idle"):
            raise ValueError("feasibility must not reverse the source decision action")
        object.__setattr__(self, "approved_power_kw", approved_power_kw)


class FeasibilityBoundary(ABC):
    """Define stateless evaluation from a decision and its exact evidence.

    ``provenance`` is explicit so an implementation never needs to reconstruct
    decision evidence. A conforming implementation returns one
    ``FeasibleDecision`` preserving both exact input references.
    """

    __slots__ = ()

    @abstractmethod
    def evaluate(
        self,
        decision: EMSDecision,
        *,
        provenance: DecisionProvenance,
    ) -> FeasibleDecision:
        """Return an approved result without execution or retained state."""
        raise NotImplementedError
