"""Tests for immutable objective activation contracts."""

import ast
import inspect
from abc import ABC
from dataclasses import FrozenInstanceError, fields
from typing import Any, cast, get_type_hints

import pytest

from objective import (
    ActiveObjectiveCollection,
    ObjectiveActivationBoundary,
    ObjectiveCollection,
    ObjectiveDescriptor,
)
from objective import activation as activation_module


class RecordingActivation(ObjectiveActivationBoundary):
    """Test-only activation with caller-visible exactly-once evidence."""

    __slots__ = ("calls",)

    def __init__(self) -> None:
        self.calls = 0

    def activate(
        self,
        objectives: ObjectiveCollection,
    ) -> ActiveObjectiveCollection:
        self.calls += 1
        return ActiveObjectiveCollection(objectives, objectives.objectives)


def make_source() -> tuple[
    ObjectiveCollection,
    ObjectiveDescriptor,
    ObjectiveDescriptor,
]:
    first = ObjectiveDescriptor("first", "First test-only concern.")
    second = ObjectiveDescriptor("second", "Second test-only concern.")
    return ObjectiveCollection((first, second)), first, second


def test_activation_boundary_is_abstract() -> None:
    assert issubclass(ObjectiveActivationBoundary, ABC)
    assert inspect.isabstract(ObjectiveActivationBoundary)
    with pytest.raises(TypeError):
        ObjectiveActivationBoundary()  # type: ignore[abstract]


def test_activate_contract_is_explicit() -> None:
    parameters = list(
        inspect.signature(ObjectiveActivationBoundary.activate).parameters
    )
    hints = get_type_hints(ObjectiveActivationBoundary.activate)

    assert parameters == ["self", "objectives"]
    assert hints == {
        "objectives": ObjectiveCollection,
        "return": ActiveObjectiveCollection,
    }


def test_activation_executes_exactly_once_and_preserves_source_identity() -> None:
    source, first, second = make_source()
    activation = RecordingActivation()

    result = activation.activate(source)

    assert activation.calls == 1
    assert result.source_collection is source
    assert result.active_objectives is source.objectives
    assert result.active_objectives[0] is first
    assert result.active_objectives[1] is second


def test_active_collection_preserves_subset_identity_and_order() -> None:
    source, first, second = make_source()
    selected = (second, first)

    result = ActiveObjectiveCollection(source, selected)

    assert result.source_collection is source
    assert result.active_objectives is selected
    assert result.active_objectives == (second, first)


def test_empty_activation_preserves_exact_empty_tuple() -> None:
    source, _, _ = make_source()
    selected: tuple[ObjectiveDescriptor, ...] = ()

    result = ActiveObjectiveCollection(source, selected)

    assert result.active_objectives is selected


def test_active_collection_rejects_invalid_types() -> None:
    source, first, _ = make_source()

    with pytest.raises(TypeError, match="source_collection"):
        ActiveObjectiveCollection(cast(Any, None), ())
    with pytest.raises(TypeError, match="active_objectives"):
        ActiveObjectiveCollection(source, cast(Any, [first]))
    with pytest.raises(TypeError, match="ObjectiveDescriptor"):
        ActiveObjectiveCollection(source, cast(Any, ("not a descriptor",)))


def test_active_collection_rejects_equal_but_reconstructed_descriptor() -> None:
    source, first, _ = make_source()
    reconstructed = ObjectiveDescriptor(first.name, first.description)

    assert reconstructed == first
    assert reconstructed is not first
    with pytest.raises(ValueError, match="identity"):
        ActiveObjectiveCollection(source, (reconstructed,))


def test_active_collection_is_frozen_slotted_and_deeply_immutable() -> None:
    source, first, _ = make_source()
    result = ActiveObjectiveCollection(source, (first,))

    assert [field.name for field in fields(ActiveObjectiveCollection)] == [
        "source_collection",
        "active_objectives",
    ]
    assert ActiveObjectiveCollection.__slots__ == (
        "source_collection",
        "active_objectives",
    )
    assert not hasattr(result, "__dict__")
    assert isinstance(result.active_objectives, tuple)
    with pytest.raises(FrozenInstanceError):
        cast(Any, result).active_objectives = ()


def test_abstract_boundary_has_no_instance_state() -> None:
    assert ObjectiveActivationBoundary.__slots__ == ()
    for forbidden in (
        "priority",
        "ranking",
        "weight",
        "score",
        "resolver",
        "intent",
        "cache",
        "history",
        "runtime",
    ):
        assert not hasattr(ObjectiveActivationBoundary, forbidden)


def test_activation_module_has_no_forbidden_dependencies() -> None:
    source = inspect.getsource(activation_module)
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {"abc", "dataclasses", "objective.model"}


def test_no_concrete_production_activation_is_introduced() -> None:
    production_boundaries = [
        value
        for value in vars(activation_module).values()
        if inspect.isclass(value)
        and value.__module__ == activation_module.__name__
        and issubclass(value, ObjectiveActivationBoundary)
    ]

    assert production_boundaries == [ObjectiveActivationBoundary]
    assert inspect.isabstract(production_boundaries[0])


def test_public_exports_include_activation_contracts() -> None:
    from objective import __all__ as public_names

    assert public_names == [
        "ActiveObjectiveCollection",
        "EMSObjectiveBoundary",
        "ObjectiveActivationBoundary",
        "ObjectiveCapabilityMapping",
        "ObjectiveCapabilityMappingBoundary",
        "ObjectiveCapabilityMappingCollection",
        "ObjectiveCollection",
        "ObjectiveDescriptor",
    ]
