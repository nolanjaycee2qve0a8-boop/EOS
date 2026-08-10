"""Concrete self-consumption strategy for Phase 9 EMS decisions."""

from typing import ClassVar

from decision_formation import DecisionIntent
from ems_strategy.boundary import EMSStrategyBoundary
from ems_strategy.context import EMSContext
from ems_strategy.decision import EMSDecision
from ems_strategy.descriptor import EMSStrategyDescriptor


class SelfConsumptionStrategy(EMSStrategyBoundary):
    """Request Battery behavior from instantaneous PV, Load, and SOC facts.

    The strategy produces an unconstrained request. Physical SOC enforcement,
    power clipping, Grid constraints, and execution remain downstream.
    """

    __slots__ = ()

    descriptor: ClassVar[EMSStrategyDescriptor] = EMSStrategyDescriptor(
        "self-consumption",
        "1.0",
    )

    def evaluate(self, context: EMSContext) -> EMSDecision:
        """Return one request preserving the exact supplied context identity."""
        if not isinstance(context, EMSContext):
            raise TypeError("context must be an EMSContext")

        facts = context.source_context
        if facts.pv_power_kw > facts.load_power_kw:
            intent = DecisionIntent("charge")
            requested_power_kw = facts.pv_power_kw - facts.load_power_kw
        elif facts.load_power_kw > facts.pv_power_kw and facts.soc > facts.reserve_soc:
            intent = DecisionIntent("discharge")
            requested_power_kw = facts.load_power_kw - facts.pv_power_kw
        else:
            intent = DecisionIntent("idle")
            requested_power_kw = 0.0

        return EMSDecision(
            source_context=context,
            source_strategy=self.descriptor,
            intent=intent,
            requested_power_kw=requested_power_kw,
        )
