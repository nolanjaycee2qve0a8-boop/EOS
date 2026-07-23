"""Immutable record of one deterministic EMS policy execution."""

from dataclasses import dataclass

from kernel.context import EnergySystemContext
from kernel.decision import DecisionResult
from kernel.execution import PolicyExecutor
from kernel.policy import EMSPolicy


@dataclass(frozen=True, slots=True)
class EMSCycle:
    """Pair one immutable system context with its exact decision result."""

    context: EnergySystemContext
    result: DecisionResult

    def __post_init__(self) -> None:
        if not isinstance(self.context, EnergySystemContext):
            raise TypeError("context must be an EnergySystemContext")
        if not isinstance(self.result, DecisionResult):
            raise TypeError("result must be a DecisionResult")

    @classmethod
    def execute(
        cls,
        policy: EMSPolicy,
        context: EnergySystemContext,
    ) -> "EMSCycle":
        """Execute one supplied policy through PolicyExecutor and record the result."""
        result = PolicyExecutor.execute(policy, context)
        return cls(context=context, result=result)
