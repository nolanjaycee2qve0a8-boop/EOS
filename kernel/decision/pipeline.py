"""Single-call orchestration boundary for deterministic decision logic."""

from dataclasses import dataclass

from kernel.decision.policy import DecisionPolicy
from kernel.decision.result import DecisionResult
from kernel.domain import Mission, Snapshot


@dataclass(frozen=True, slots=True)
class DecisionPipeline:
    """Apply one policy once to one immutable snapshot and mission."""

    policy: DecisionPolicy

    def __post_init__(self) -> None:
        if not isinstance(self.policy, DecisionPolicy):
            raise TypeError("policy must satisfy the DecisionPolicy contract")

    def execute(self, snapshot: Snapshot, mission: Mission) -> DecisionResult:
        """Validate inputs, invoke the policy once, and return its exact result."""
        if not isinstance(snapshot, Snapshot):
            raise TypeError("snapshot must be a Snapshot")
        if not isinstance(mission, Mission):
            raise TypeError("mission must be a Mission")

        result = self.policy.decide(snapshot, mission)
        if not isinstance(result, DecisionResult):
            raise TypeError("policy must return a DecisionResult")
        return result
