"""Tests for the structural DecisionPolicy contract."""

from kernel.decision import DecisionPolicy, DecisionResult
from kernel.domain import Mission, Snapshot


class CompatiblePolicy:
    def decide(self, snapshot: Snapshot, mission: Mission) -> DecisionResult:
        return DecisionResult.empty()


class IncompatiblePolicy:
    pass


def test_structurally_compatible_policy_satisfies_protocol() -> None:
    assert isinstance(CompatiblePolicy(), DecisionPolicy)


def test_incompatible_object_does_not_satisfy_protocol() -> None:
    assert not isinstance(IncompatiblePolicy(), DecisionPolicy)


def test_policy_does_not_require_framework_inheritance() -> None:
    assert CompatiblePolicy.__bases__ == (object,)
