"""Tests for the public policy import boundaries."""

import kernel.policy as policy
from kernel.policy import (
    DecisionContextPolicy,
    DecisionEvaluationOrchestrator,
    EMSPolicy,
)


def test_policy_boundaries_are_publicly_importable() -> None:
    assert DecisionContextPolicy.__name__ == "DecisionContextPolicy"
    assert DecisionEvaluationOrchestrator.__name__ == "DecisionEvaluationOrchestrator"
    assert EMSPolicy.__name__ == "EMSPolicy"


def test_policy_package_exports_both_independent_boundaries() -> None:
    assert policy.__all__ == [
        "DecisionContextPolicy",
        "DecisionEvaluationOrchestrator",
        "EMSPolicy",
    ]
