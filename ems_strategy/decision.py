"""Immutable request produced by a future EMS strategy implementation."""

from dataclasses import dataclass
from math import isfinite

from decision_formation import DecisionIntent
from ems_strategy.context import EMSContext
from ems_strategy.descriptor import EMSStrategyDescriptor


def _require_requested_power(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("requested_power_kw must be a number")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError("requested_power_kw must be finite")
    if normalized < 0:
        raise ValueError("requested_power_kw must be greater than or equal to 0")
    return normalized


@dataclass(frozen=True, slots=True)
class EMSDecision:
    """Preserve one strategy request and its exact provenance.

    ``requested_power_kw`` is a non-negative raw kW magnitude. Direction is
    expressed only by ``intent.action``: charge and discharge require a
    positive magnitude, while idle requires zero. This request is neither a
    feasible decision, a simulation actuation, nor a device command.
    """

    source_context: EMSContext
    source_strategy: EMSStrategyDescriptor
    intent: DecisionIntent
    requested_power_kw: float

    def __post_init__(self) -> None:
        if not isinstance(self.source_context, EMSContext):
            raise TypeError("source_context must be an EMSContext")
        if not isinstance(self.source_strategy, EMSStrategyDescriptor):
            raise TypeError("source_strategy must be an EMSStrategyDescriptor")
        if not isinstance(self.intent, DecisionIntent):
            raise TypeError("intent must be a DecisionIntent")

        requested_power_kw = _require_requested_power(self.requested_power_kw)
        if self.intent.action == "idle" and requested_power_kw != 0:
            raise ValueError("idle intent requires requested_power_kw equal to 0")
        if self.intent.action != "idle" and requested_power_kw == 0:
            raise ValueError(
                "charge and discharge intents require requested_power_kw greater than 0"
            )
        object.__setattr__(self, "requested_power_kw", requested_power_kw)
