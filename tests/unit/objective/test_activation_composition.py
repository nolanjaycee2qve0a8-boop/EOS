"""Tests for objective-to-active-capability composition contracts."""

import ast
import inspect
from abc import ABC
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import Any, cast, get_type_hints

import pytest

import capability
from capability import (
    ActiveCapabilityCollection,
    AvailableCapabilityCollection,
    CapabilityDescriptor,
    CapabilityMatch,
    CapabilityMatchCollection,
    RequiredCapabilityCollection,
)
from objective import (
    ObjectiveCapabilityActivationComposition,
    ObjectiveCapabilityActivationCompositionBoundary,
    ObjectiveDescriptor,
)
from objective import activation_composition as composition_module


class RecordingCompositionBoundary(ObjectiveCapabilityActivationCompositionBoundary):
    """Test-only boundary with exactly-once call evidence."""

    __slots__ = ("calls",)

    def __init__(self) -> None:
        self.calls = 0

    def compose(
        self,
        objective: ObjectiveDescriptor,
        active_capabilities: ActiveCapabilityCollection,
    ) -> ObjectiveCapabilityActivationComposition:
        self.calls += 1
        return ObjectiveCapabilityActivationComposition(
            objective,
            active_capabilities,
        )


def make_active_capabilities() -> tuple[
    ActiveCapabilityCollection,
    CapabilityDescriptor,
    CapabilityDescriptor,
]:
    required_first = CapabilityDescriptor("required-first", "First requirement.")
    required_second = CapabilityDescriptor("required-second", "Second requirement.")
    available_first = CapabilityDescriptor("available-first", "First availability.")
    available_second = CapabilityDescriptor("available-second", "Second availability.")
    required = RequiredCapabilityCollection((required_first, required_second))
    available = AvailableCapabilityCollection((available_first, available_second))
    matches = (
        CapabilityMatch(required_first, available_first),
        CapabilityMatch(required_second, available_second),
    )
    match_collection = CapabilityMatchCollection(required, available, matches, ())
    active = ActiveCapabilityCollection(
        match_collection,
        (available_first, available_second),
        (),
    )
    return active, available_first, available_second


def test_composition_boundary_is_abstract_and_stateless() -> None:
    assert issubclass(ObjectiveCapabilityActivationCompositionBoundary, ABC)
    assert inspect.isabstract(ObjectiveCapabilityActivationCompositionBoundary)
    assert ObjectiveCapabilityActivationCompositionBoundary.__slots__ == ()
    with pytest.raises(TypeError):
        ObjectiveCapabilityActivationCompositionBoundary()  # type: ignore[abstract]


def test_composition_boundary_signature_is_explicit() -> None:
    parameters = list(
        inspect.signature(
            ObjectiveCapabilityActivationCompositionBoundary.compose
        ).parameters
    )
    hints = get_type_hints(ObjectiveCapabilityActivationCompositionBoundary.compose)

    assert parameters == ["self", "objective", "active_capabilities"]
    assert hints == {
        "objective": ObjectiveDescriptor,
        "active_capabilities": ActiveCapabilityCollection,
        "return": ObjectiveCapabilityActivationComposition,
    }


def test_composition_preserves_objective_and_collection_identities() -> None:
    objective = ObjectiveDescriptor("cost", "Reduce energy cost.")
    active, first, second = make_active_capabilities()

    composition = ObjectiveCapabilityActivationComposition(objective, active)

    assert composition.objective is objective
    assert composition.active_capabilities is active
    assert composition.active_capabilities.active_capabilities[0] is first
    assert composition.active_capabilities.active_capabilities[1] is second


def test_composition_is_complete_by_retaining_exact_active_collection() -> None:
    objective = ObjectiveDescriptor("complete", "Use all active capabilities.")
    active, _, _ = make_active_capabilities()
    active_tuple = active.active_capabilities

    composition = ObjectiveCapabilityActivationComposition(objective, active)

    assert composition.active_capabilities is active
    assert composition.active_capabilities.active_capabilities is active_tuple
    assert len(composition.active_capabilities.active_capabilities) == 2


def test_empty_active_collection_is_complete_and_valid() -> None:
    objective = ObjectiveDescriptor("empty", "No active capability required.")
    required = RequiredCapabilityCollection(())
    available = AvailableCapabilityCollection(())
    matches = CapabilityMatchCollection(required, available, (), ())
    active = ActiveCapabilityCollection(matches, (), ())

    composition = ObjectiveCapabilityActivationComposition(objective, active)

    assert composition.objective is objective
    assert composition.active_capabilities is active
    assert composition.active_capabilities.active_capabilities == ()


def test_composition_rejects_duplicate_active_capability_identity() -> None:
    objective = ObjectiveDescriptor("duplicate", "Reject duplicate identities.")
    active, first, _ = make_active_capabilities()
    duplicated = ActiveCapabilityCollection(
        active.source_collection,
        (first, first),
        (active.active_capabilities[1],),
    )

    with pytest.raises(ValueError, match="duplicate"):
        ObjectiveCapabilityActivationComposition(objective, duplicated)


def test_reconstructed_capability_cannot_enter_active_source() -> None:
    objective = ObjectiveDescriptor("identity", "Preserve exact identities.")
    active, first, second = make_active_capabilities()
    reconstructed = CapabilityDescriptor(first.name, first.description)

    assert reconstructed == first
    assert reconstructed is not first
    with pytest.raises(ValueError, match="identity"):
        ActiveCapabilityCollection(
            active.source_collection,
            (reconstructed, second),
            (),
        )
    assert objective.name == "identity"


def test_composition_boundary_executes_exactly_once() -> None:
    objective = ObjectiveDescriptor("once", "Compose exactly once.")
    active, _, _ = make_active_capabilities()
    boundary = RecordingCompositionBoundary()

    result = boundary.compose(objective, active)

    assert boundary.calls == 1
    assert result.objective is objective
    assert result.active_capabilities is active


def test_composition_rejects_invalid_types() -> None:
    objective = ObjectiveDescriptor("types", "Validate input types.")
    active, _, _ = make_active_capabilities()

    with pytest.raises(TypeError, match="objective"):
        ObjectiveCapabilityActivationComposition(cast(Any, None), active)
    with pytest.raises(TypeError, match="active_capabilities"):
        ObjectiveCapabilityActivationComposition(objective, cast(Any, None))


def test_composition_is_frozen_slotted_and_contains_no_mutable_collection() -> None:
    objective = ObjectiveDescriptor("immutable", "Remain immutable.")
    active, _, _ = make_active_capabilities()
    composition = ObjectiveCapabilityActivationComposition(objective, active)

    assert [
        field.name for field in fields(ObjectiveCapabilityActivationComposition)
    ] == ["objective", "active_capabilities"]
    assert ObjectiveCapabilityActivationComposition.__slots__ == (
        "objective",
        "active_capabilities",
    )
    assert not hasattr(composition, "__dict__")
    assert isinstance(composition.active_capabilities.active_capabilities, tuple)
    with pytest.raises(FrozenInstanceError):
        cast(Any, composition).objective = objective


def test_composition_module_has_contract_only_dependencies() -> None:
    source = inspect.getsource(composition_module)
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "capability.activation",
        "dataclasses",
        "objective.model",
    }


def test_capability_package_has_no_objective_dependency() -> None:
    package_path = Path(capability.__file__).parent
    for module_path in package_path.glob("*.py"):
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        imported_modules = {
            node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        }
        assert all(
            module is None or not module.startswith("objective")
            for module in imported_modules
        )


def test_no_concrete_production_composition_is_introduced() -> None:
    production_boundaries = [
        value
        for value in vars(composition_module).values()
        if inspect.isclass(value)
        and value.__module__ == composition_module.__name__
        and issubclass(value, ObjectiveCapabilityActivationCompositionBoundary)
    ]

    assert production_boundaries == [ObjectiveCapabilityActivationCompositionBoundary]
    assert inspect.isabstract(production_boundaries[0])


def test_boundary_has_no_selection_execution_or_intent_contract() -> None:
    for forbidden in (
        "select",
        "rank",
        "priority",
        "score",
        "optimize",
        "resolve",
        "fallback",
        "evaluate",
        "intent",
        "constraint",
        "runtime",
        "device",
        "cache",
        "history",
    ):
        assert not hasattr(
            ObjectiveCapabilityActivationCompositionBoundary,
            forbidden,
        )


def test_public_exports_include_activation_composition_contracts() -> None:
    from objective import __all__ as public_names

    assert "ObjectiveCapabilityActivationComposition" in public_names
    assert "ObjectiveCapabilityActivationCompositionBoundary" in public_names
