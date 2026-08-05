"""Tests for the Phase 5 decision formation public API."""

from typing import cast

from decision_formation import (
    DecisionFormationBoundary,
    DecisionFormationInput,
    DecisionIntent,
    DecisionIntentCandidate,
)
from decision_formation import __all__ as public_names
from kernel.decision import DecisionIntent as LegacyDecisionIntent


def test_decision_intent_public_import() -> None:
    intent = DecisionIntent("idle")

    assert intent.action == "idle"
    assert public_names == [
        "DecisionFormationBoundary",
        "DecisionFormationInput",
        "DecisionIntent",
        "DecisionIntentCandidate",
    ]


def test_phase5_intent_is_independent_from_legacy_numeric_intent() -> None:
    assert cast(object, DecisionIntent) is not cast(object, LegacyDecisionIntent)


def test_formation_contracts_are_public() -> None:
    assert DecisionFormationBoundary.__name__ == "DecisionFormationBoundary"
    assert DecisionFormationInput.__name__ == "DecisionFormationInput"
    assert DecisionIntentCandidate.__name__ == "DecisionIntentCandidate"
