"""Tests for the constraint explanation observation boundary."""

import ast
import inspect
from dataclasses import FrozenInstanceError, fields, is_dataclass
from typing import Any, cast

import pytest

from kernel.decision import (
    ConstraintExplanation,
    DecisionIntent,
    FeasibleDecisionIntent,
)
from kernel.decision import constraint_explanation as explanation_module


def make_feasible_intent(power_kw: float = 0.0) -> FeasibleDecisionIntent:
    return FeasibleDecisionIntent(DecisionIntent(power_kw))


def test_create_preserves_exact_source_identities() -> None:
    feasible_intent = make_feasible_intent(25.0)
    source_intent = feasible_intent.intent

    explanation = ConstraintExplanation.create(feasible_intent)

    assert explanation.feasible_intent is feasible_intent
    assert explanation.source_intent is source_intent


def test_explanation_is_frozen_and_slotted() -> None:
    explanation = ConstraintExplanation.create(make_feasible_intent())

    assert is_dataclass(explanation)
    assert cast(Any, ConstraintExplanation).__dataclass_params__.frozen
    assert ConstraintExplanation.__slots__ == (
        "feasible_intent",
        "source_intent",
    )
    assert not hasattr(explanation, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, explanation).source_intent = DecisionIntent(1.0)


def test_explanation_contains_only_source_references() -> None:
    explanation = ConstraintExplanation.create(make_feasible_intent())

    assert [field.name for field in fields(explanation)] == [
        "feasible_intent",
        "source_intent",
    ]
    for forbidden in (
        "commands",
        "events",
        "dispatch",
        "device",
        "protocol",
        "optimization_result",
        "forecast",
        "cache",
        "history",
        "runtime_state",
        "reason",
        "recommendation",
    ):
        assert not hasattr(explanation, forbidden)


def test_create_rejects_invalid_feasible_intent() -> None:
    with pytest.raises(TypeError, match="feasible_intent"):
        ConstraintExplanation.create(cast(FeasibleDecisionIntent, object()))


def test_constructor_rejects_invalid_source_intent() -> None:
    feasible_intent = make_feasible_intent()

    with pytest.raises(TypeError, match="source_intent"):
        ConstraintExplanation(
            feasible_intent,
            cast(DecisionIntent, object()),
        )


def test_constructor_rejects_broken_identity_relationship() -> None:
    feasible_intent = make_feasible_intent()

    with pytest.raises(ValueError, match="exact"):
        ConstraintExplanation(feasible_intent, DecisionIntent(0.0))


def test_explanation_module_has_no_forbidden_dependencies() -> None:
    source = inspect.getsource(explanation_module)
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "dataclasses",
        "kernel.decision.constraint",
        "kernel.decision.intent",
    }
    for forbidden in (
        "runtime",
        "dispatch",
        "device",
        "persistence",
        "telemetry",
        "optimization",
        "forecast",
    ):
        assert forbidden not in imported_modules


def test_public_import_has_explicit_name() -> None:
    assert ConstraintExplanation.__name__ == "ConstraintExplanation"
