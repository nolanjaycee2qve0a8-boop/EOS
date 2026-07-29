"""Tests for the public policy import boundaries."""

import kernel.policy as policy
from kernel.policy import (
    DecisionContextPolicy,
    DecisionContextPolicyImplementation,
    DecisionEvaluationOrchestrator,
    EMSPolicy,
    SelfConsumptionPolicy,
)


def test_policy_boundaries_are_publicly_importable() -> None:
    assert DecisionContextPolicy.__name__ == "DecisionContextPolicy"
    assert (
        DecisionContextPolicyImplementation.__name__
        == "DecisionContextPolicyImplementation"
    )
    assert DecisionEvaluationOrchestrator.__name__ == "DecisionEvaluationOrchestrator"
    assert EMSPolicy.__name__ == "EMSPolicy"
    assert SelfConsumptionPolicy.__name__ == "SelfConsumptionPolicy"


def test_policy_package_exports_both_independent_boundaries() -> None:
    assert policy.__all__ == [
        "DecisionContextPolicy",
        "DecisionContextPolicyImplementation",
        "DecisionEvaluationOrchestrator",
        "EMSPolicy",
        "SelfConsumptionPolicy",
    ]
