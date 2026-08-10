"""Explicit adapter boundary from EMS feasibility to simulation actuation."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ems_strategy.feasibility import FeasibleDecision
from simulator import BatterySimulationActuation


def _signed_battery_power(feasible_decision: FeasibleDecision) -> float:
    action = feasible_decision.approved_intent.action
    magnitude = feasible_decision.approved_power_kw
    if action == "charge":
        return magnitude
    if action == "discharge":
        return -magnitude
    return 0.0


@dataclass(frozen=True, slots=True)
class ActuationHandoffResult:
    """Relate an exact Phase 9 feasible decision to an exact actuation.

    The result is an adapter artifact between the EMS Layer and Simulator
    Layer. It does not replace either source contract. Simulator Battery power
    is signed raw kW: charge is positive, discharge is negative, and idle is
    zero.
    """

    source_feasible_decision: FeasibleDecision
    actuation: BatterySimulationActuation

    def __post_init__(self) -> None:
        if not isinstance(self.source_feasible_decision, FeasibleDecision):
            raise TypeError("source_feasible_decision must be a FeasibleDecision")
        if not isinstance(self.actuation, BatterySimulationActuation):
            raise TypeError("actuation must be a BatterySimulationActuation")
        expected_power_kw = _signed_battery_power(self.source_feasible_decision)
        if self.actuation.battery_power_kw != expected_power_kw:
            raise ValueError(
                "actuation battery_power_kw must match the feasible action and power"
            )


class ActuationHandoffBoundary(ABC):
    """Validate one stateless EMS-to-Simulator actuation handoff."""

    __slots__ = ()

    def handoff(
        self,
        feasible_decision: FeasibleDecision,
    ) -> ActuationHandoffResult:
        """Return one identity-preserving handoff without executing simulation."""
        if not isinstance(feasible_decision, FeasibleDecision):
            raise TypeError("feasible_decision must be a FeasibleDecision")
        result = self._handoff(feasible_decision)
        if not isinstance(result, ActuationHandoffResult):
            raise TypeError("handoff must return an ActuationHandoffResult")
        if result.source_feasible_decision is not feasible_decision:
            raise ValueError(
                "handoff must preserve exact source_feasible_decision identity"
            )
        return result

    @abstractmethod
    def _handoff(
        self,
        feasible_decision: FeasibleDecision,
    ) -> ActuationHandoffResult:
        """Create an actuation relationship without physics or execution."""
        raise NotImplementedError
