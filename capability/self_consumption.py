"""Stateless photovoltaic self-consumption EMS capability."""

from capability.base import EMSCapabilityBoundary
from kernel.decision import DecisionContext, DecisionIntent


class SelfConsumptionCapability(EMSCapabilityBoundary):
    """Generate battery intent from instantaneous PV-load imbalance."""

    __slots__ = ()

    def evaluate(self, context: DecisionContext) -> DecisionIntent:
        """Return raw surplus, deficit, or balanced battery power intent."""
        if not isinstance(context, DecisionContext):
            raise TypeError("context must be a DecisionContext")

        return DecisionIntent(
            battery_power_intent_kw=context.pv_power_kw - context.load_power_kw,
        )
