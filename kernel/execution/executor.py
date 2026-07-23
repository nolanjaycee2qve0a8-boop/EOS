"""Stateless adapter for one EMS policy evaluation."""

from kernel.context import EnergySystemContext
from kernel.decision import DecisionResult
from kernel.policy import EMSPolicy


class PolicyExecutor:
    """Execute a supplied EMS policy without owning policy or runtime state."""

    __slots__ = ()

    @staticmethod
    def execute(
        policy: EMSPolicy,
        context: EnergySystemContext,
    ) -> DecisionResult:
        """Evaluate one policy once and return its exact DecisionResult."""
        if not isinstance(policy, EMSPolicy):
            raise TypeError("policy must be an EMSPolicy instance")
        if not isinstance(context, EnergySystemContext):
            raise TypeError("context must be an EnergySystemContext")

        result = policy.evaluate(context)
        if not isinstance(result, DecisionResult):
            raise TypeError("policy must return a DecisionResult")
        return result
