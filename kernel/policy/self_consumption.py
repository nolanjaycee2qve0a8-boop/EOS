"""Basic photovoltaic self-consumption decision policy."""

from kernel.decision.context import DecisionContext
from kernel.decision.context_result import DecisionContextResult
from kernel.decision.intent import DecisionIntent
from kernel.policy.implementation import DecisionContextPolicyImplementation


class SelfConsumptionPolicy(DecisionContextPolicyImplementation):
    """Express battery intent from the instantaneous PV-load imbalance."""

    __slots__ = ()

    def evaluate(self, context: DecisionContext) -> DecisionContextResult:
        """Return charging, discharging, or idle intent for PV self-consumption."""
        if not isinstance(context, DecisionContext):
            raise TypeError("context must be a DecisionContext")

        if context.pv_power_kw > context.load_power_kw:
            battery_power_intent_kw = context.pv_power_kw - context.load_power_kw
        elif context.load_power_kw > context.pv_power_kw:
            battery_power_intent_kw = -(context.load_power_kw - context.pv_power_kw)
        else:
            battery_power_intent_kw = 0.0

        intent = DecisionIntent(
            battery_power_intent_kw=battery_power_intent_kw,
        )
        return DecisionContextResult(intent=intent)
