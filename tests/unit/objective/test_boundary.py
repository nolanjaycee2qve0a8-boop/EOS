"""Tests for the EMS objective boundary."""

import ast
import inspect
from abc import ABC
from typing import Any, cast, get_type_hints

import pytest

from objective import EMSObjectiveBoundary, ObjectiveCollection
from objective import base as objective_base_module

EMPTY_OBJECTIVES = ObjectiveCollection(())


class MinimalObjectiveBoundary(EMSObjectiveBoundary):
    """Test-only boundary with no concrete production objective."""

    __slots__ = ()

    def describe(self) -> ObjectiveCollection:
        return EMPTY_OBJECTIVES


def test_objective_boundary_is_abstract() -> None:
    assert issubclass(EMSObjectiveBoundary, ABC)
    assert inspect.isabstract(EMSObjectiveBoundary)
    with pytest.raises(TypeError):
        EMSObjectiveBoundary()  # type: ignore[abstract]


def test_describe_contract_returns_objective_collection() -> None:
    parameters = list(inspect.signature(EMSObjectiveBoundary.describe).parameters)
    hints = get_type_hints(EMSObjectiveBoundary.describe)

    assert parameters == ["self"]
    assert hints == {"return": ObjectiveCollection}


def test_test_boundary_returns_exact_collection_identity() -> None:
    result = MinimalObjectiveBoundary().describe()

    assert result is EMPTY_OBJECTIVES


def test_boundary_has_no_instance_state() -> None:
    boundary = MinimalObjectiveBoundary()

    assert EMSObjectiveBoundary.__slots__ == ()
    assert not hasattr(boundary, "__dict__")
    for forbidden in (
        "priority",
        "weight",
        "score",
        "resolver",
        "intent",
        "cache",
        "history",
        "runtime",
    ):
        assert not hasattr(boundary, forbidden)
    with pytest.raises(AttributeError):
        cast(Any, boundary).cache = {}


def test_boundary_module_depends_only_on_objective_contracts() -> None:
    source = inspect.getsource(objective_base_module)
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {"abc", "objective.model"}


def test_no_concrete_production_objective_is_introduced() -> None:
    production_classes = [
        value
        for value in vars(objective_base_module).values()
        if inspect.isclass(value) and value.__module__ == objective_base_module.__name__
    ]

    assert production_classes == [EMSObjectiveBoundary]
    assert inspect.isabstract(production_classes[0])


def test_public_imports_are_exact() -> None:
    from objective import __all__ as public_names

    assert public_names == [
        "ActiveObjectiveCollection",
        "EMSObjectiveBoundary",
        "ObjectiveActivationBoundary",
        "ObjectiveCapabilityActivationComposition",
        "ObjectiveCapabilityActivationCompositionBoundary",
        "ObjectiveCapabilityMapping",
        "ObjectiveCapabilityMappingBoundary",
        "ObjectiveCapabilityMappingCollection",
        "ObjectiveCollection",
        "ObjectiveDescriptor",
    ]
