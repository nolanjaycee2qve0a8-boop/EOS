"""Tests for the grid constraint abstraction boundary."""

import ast
import inspect
from abc import ABC
from typing import get_type_hints

import pytest

from kernel.decision import (
    DecisionConstraintBoundary,
    DecisionIntent,
    FeasibleDecisionIntent,
    GridConstraintBoundary,
)
from kernel.decision import grid_constraint as grid_constraint_module


class AcceptingGridConstraint(GridConstraintBoundary):
    """Test-only implementation that accepts the supplied intent."""

    __slots__ = ()

    def evaluate(self, intent: DecisionIntent) -> FeasibleDecisionIntent:
        return FeasibleDecisionIntent(intent)


def test_grid_constraint_boundary_is_abstract_and_stateless() -> None:
    assert issubclass(GridConstraintBoundary, ABC)
    assert issubclass(GridConstraintBoundary, DecisionConstraintBoundary)
    assert inspect.isabstract(GridConstraintBoundary)
    assert GridConstraintBoundary.__slots__ == ()
    assert getattr(
        GridConstraintBoundary.evaluate,
        "__isabstractmethod__",
        False,
    )
    with pytest.raises(TypeError):
        GridConstraintBoundary()  # type: ignore[abstract]


def test_evaluate_preserves_the_generic_constraint_contract() -> None:
    parameters = list(inspect.signature(GridConstraintBoundary.evaluate).parameters)
    hints = get_type_hints(GridConstraintBoundary.evaluate)

    assert parameters == ["self", "intent"]
    assert hints == {
        "intent": DecisionIntent,
        "return": FeasibleDecisionIntent,
    }
    assert inspect.signature(GridConstraintBoundary.evaluate) == inspect.signature(
        DecisionConstraintBoundary.evaluate,
    )


def test_test_only_implementation_preserves_exact_intent_identity() -> None:
    intent = DecisionIntent(8.0)
    boundary = AcceptingGridConstraint()

    feasible_intent = boundary.evaluate(intent)

    assert feasible_intent.intent is intent
    assert not hasattr(boundary, "__dict__")


def test_boundary_defines_no_grid_facts_or_mutable_state() -> None:
    boundary = AcceptingGridConstraint()

    for field_name in (
        "grid_import_limit_kw",
        "grid_export_limit_kw",
        "zero_export",
        "cache",
        "history",
        "runtime_state",
    ):
        assert not hasattr(boundary, field_name)


def test_module_introduces_no_concrete_production_constraint() -> None:
    source = inspect.getsource(grid_constraint_module)
    tree = ast.parse(source)
    classes = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]

    assert classes == ["GridConstraintBoundary"]


def test_module_has_only_boundary_dependencies() -> None:
    source = inspect.getsource(grid_constraint_module)
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
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
        "pricing",
    ):
        assert forbidden not in imported_modules


def test_public_import_has_explicit_name() -> None:
    assert GridConstraintBoundary.__name__ == "GridConstraintBoundary"
