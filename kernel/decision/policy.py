"""Structural contract for deterministic EOS decision logic."""

from typing import Protocol, runtime_checkable

from kernel.decision.result import DecisionResult
from kernel.domain import Mission, Snapshot


@runtime_checkable
class DecisionPolicy(Protocol):
    """Pure decision logic applied to one snapshot and one mission."""

    def decide(self, snapshot: Snapshot, mission: Mission) -> DecisionResult:
        """Return deterministic outputs for the supplied immutable inputs."""
        ...
