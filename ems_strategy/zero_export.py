"""Zero Export feasibility evidence and abstract evaluation boundary."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ems_strategy.decision import EMSDecision
from ems_strategy.provenance import DecisionProvenance


@dataclass(frozen=True, slots=True)
class ZeroExportFeasibility:
    """Record whether one exact decision is feasible for Zero Export.

    The artifact only records a feasibility fact. It does not correct power,
    replace the source request, or perform physical control.
    """

    source_decision: EMSDecision
    source_provenance: DecisionProvenance
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
        if not isinstance(self.is_feasible, bool):
            raise TypeError("is_feasible must be a bool")


class ZeroExportBoundary(ABC):
    """Define stateless Zero Export feasibility evaluation without correction."""

    __slots__ = ()

    def evaluate(
        self,
        decision: EMSDecision,
        *,
        provenance: DecisionProvenance,
    ) -> ZeroExportFeasibility:
        """Return one identity-preserving Zero Export feasibility fact."""
        if not isinstance(decision, EMSDecision):
            raise TypeError("decision must be an EMSDecision")
        if not isinstance(provenance, DecisionProvenance):
            raise TypeError("provenance must be a DecisionProvenance")
        if provenance.decision is not decision:
            raise ValueError("provenance must preserve exact decision identity")

        result = self._evaluate(decision, provenance=provenance)
        if not isinstance(result, ZeroExportFeasibility):
            raise TypeError("evaluate must return a ZeroExportFeasibility")
        if result.source_decision is not decision:
            raise ValueError("result must preserve exact source_decision identity")
        if result.source_provenance is not provenance:
            raise ValueError("result must preserve exact source_provenance identity")
        return result

    @abstractmethod
    def _evaluate(
        self,
        decision: EMSDecision,
        *,
        provenance: DecisionProvenance,
    ) -> ZeroExportFeasibility:
        """Represent feasibility without power correction or retained state."""
        raise NotImplementedError
