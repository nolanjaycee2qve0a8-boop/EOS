"""Tests for the decision constraint boundary."""

import ast
import inspect
from abc import ABC
from dataclasses import FrozenInstanceError, fields, is_dataclass
from typing import Any, cast, get_type_hints

import pytest

from kernel.decision import (
    DecisionConstraintBoundary,
    DecisionIntent,
    FeasibleDecisionIntent,
)
from kernel.decision import constraint as constraint_module


class AcceptingConstraint(DecisionConstraintBoundary):
    """Test-only boundary implementation."""

    __slots__ = ("received_intent",)

    def __init__(self) -> None:
        self.received_intent: DecisionIntent | None = None

    def evaluate(self, intent: DecisionIntent) -> FeasibleDecisionIntent:
        self.received_intent = intent
        return FeasibleDecisionIntent(intent)


def test_constraint_boundary_is_abstract_and_stateless() -> None:
    assert issubclass(DecisionConstraintBoundary, ABC)
    assert inspect.isabstract(DecisionConstraintBoundary)
    assert DecisionConstraintBoundary.__slots__ == ()
    assert getattr(
        DecisionConstraintBoundary.evaluate,
        "__isabstractmethod__",
        False,
    )
    with pytest.raises(TypeError):
        DecisionConstraintBoundary()  # type: ignore[abstract]


def test_evaluate_contract_accepts_intent_and_returns_feasible_intent() -> None:
    parameters = list(inspect.signature(DecisionConstraintBoundary.evaluate).parameters)
    hints = get_type_hints(DecisionConstraintBoundary.evaluate)

    assert parameters == ["self", "intent"]
    assert hints == {
        "intent": DecisionIntent,
        "return": FeasibleDecisionIntent,
    }


def test_boundary_preserves_exact_intent_identity() -> None:
    intent = DecisionIntent(25.0)
    boundary = AcceptingConstraint()

    result = boundary.evaluate(intent)

    assert boundary.received_intent is intent
    assert result.intent is intent


def test_feasible_intent_is_frozen_and_slotted() -> None:
    result = FeasibleDecisionIntent(DecisionIntent(0.0))

    assert is_dataclass(result)
    assert cast(Any, FeasibleDecisionIntent).__dataclass_params__.frozen
    assert FeasibleDecisionIntent.__slots__ == ("intent",)
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, result).intent = DecisionIntent(1.0)


def test_feasible_intent_has_only_original_intent_reference() -> None:
    result = FeasibleDecisionIntent(DecisionIntent(0.0))

    assert [field.name for field in fields(result)] == ["intent"]
    for forbidden in (
        "commands",
        "events",
        "cache",
        "history",
        "runtime_state",
        "dispatch",
    ):
        assert not hasattr(result, forbidden)


def test_feasible_intent_rejects_invalid_input_type() -> None:
    with pytest.raises(TypeError, match="intent"):
        FeasibleDecisionIntent(cast(DecisionIntent, object()))


def test_constraint_module_has_no_forbidden_dependencies() -> None:
    source = inspect.getsource(constraint_module)
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "dataclasses",
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


def test_public_imports_have_explicit_names() -> None:
    assert DecisionConstraintBoundary.__name__ == "DecisionConstraintBoundary"
    assert FeasibleDecisionIntent.__name__ == "FeasibleDecisionIntent"
