"""Tests for objective-to-capability descriptor mapping contracts."""

import ast
import inspect
from abc import ABC
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import Any, cast, get_type_hints

import pytest

import capability
from capability import CapabilityDescriptor, EMSCapabilityBoundary
from objective import (
    ActiveObjectiveCollection,
    ObjectiveCapabilityMapping,
    ObjectiveCapabilityMappingBoundary,
    ObjectiveCapabilityMappingCollection,
    ObjectiveCollection,
    ObjectiveDescriptor,
)
from objective import mapping as mapping_module


class EmptyTestMappingBoundary(ObjectiveCapabilityMappingBoundary):
    """Test-only mapping boundary without production mapping rules."""

    __slots__ = ()

    def map_objectives(
        self,
        objectives: ObjectiveCollection | ActiveObjectiveCollection,
    ) -> ObjectiveCapabilityMappingCollection:
        return ObjectiveCapabilityMappingCollection(objectives, ())


def make_objectives() -> tuple[
    ObjectiveCollection,
    ObjectiveDescriptor,
    ObjectiveDescriptor,
]:
    first = ObjectiveDescriptor("first", "First test-only objective.")
    second = ObjectiveDescriptor("second", "Second test-only objective.")
    return ObjectiveCollection((first, second)), first, second


def make_capabilities() -> tuple[CapabilityDescriptor, CapabilityDescriptor]:
    first = CapabilityDescriptor("first", "First test-only capability.")
    second = CapabilityDescriptor("second", "Second test-only capability.")
    return first, second


def test_mapping_boundary_is_abstract_and_stateless() -> None:
    assert issubclass(ObjectiveCapabilityMappingBoundary, ABC)
    assert inspect.isabstract(ObjectiveCapabilityMappingBoundary)
    assert ObjectiveCapabilityMappingBoundary.__slots__ == ()
    with pytest.raises(TypeError):
        ObjectiveCapabilityMappingBoundary()  # type: ignore[abstract]


def test_mapping_boundary_signature_accepts_immutable_sources() -> None:
    parameters = list(
        inspect.signature(ObjectiveCapabilityMappingBoundary.map_objectives).parameters
    )
    hints = get_type_hints(ObjectiveCapabilityMappingBoundary.map_objectives)

    assert parameters == ["self", "objectives"]
    assert hints == {
        "objectives": ObjectiveCollection | ActiveObjectiveCollection,
        "return": ObjectiveCapabilityMappingCollection,
    }


def test_empty_mapping_preserves_source_identity() -> None:
    source, _, _ = make_objectives()

    result = EmptyTestMappingBoundary().map_objectives(source)

    assert result.source_collection is source
    assert result.mappings == ()


def test_mapping_preserves_descriptor_and_tuple_identities() -> None:
    source, objective, _ = make_objectives()
    first_capability, second_capability = make_capabilities()
    capabilities = (first_capability, second_capability)
    mapping = ObjectiveCapabilityMapping(objective, capabilities)
    mappings = (mapping,)

    collection = ObjectiveCapabilityMappingCollection(source, mappings)

    assert mapping.objective is objective
    assert mapping.capabilities is capabilities
    assert mapping.capabilities[0] is first_capability
    assert mapping.capabilities[1] is second_capability
    assert collection.source_collection is source
    assert collection.mappings is mappings
    assert collection.mappings[0] is mapping


def test_mapping_can_express_no_supporting_capabilities() -> None:
    source, objective, _ = make_objectives()
    capabilities: tuple[CapabilityDescriptor, ...] = ()
    mapping = ObjectiveCapabilityMapping(objective, capabilities)

    collection = ObjectiveCapabilityMappingCollection(source, (mapping,))

    assert mapping.capabilities is capabilities
    assert collection.mappings[0] is mapping


def test_mapping_accepts_exact_active_objective_source() -> None:
    source, _, active_objective = make_objectives()
    active = ActiveObjectiveCollection(source, (active_objective,))
    mapping = ObjectiveCapabilityMapping(active_objective, ())

    collection = ObjectiveCapabilityMappingCollection(active, (mapping,))

    assert collection.source_collection is active
    assert collection.mappings[0].objective is active_objective


def test_collection_rejects_equal_but_reconstructed_objective() -> None:
    source, objective, _ = make_objectives()
    reconstructed = ObjectiveDescriptor(objective.name, objective.description)
    mapping = ObjectiveCapabilityMapping(reconstructed, ())

    assert reconstructed == objective
    assert reconstructed is not objective
    with pytest.raises(ValueError, match="identity"):
        ObjectiveCapabilityMappingCollection(source, (mapping,))


def test_models_reject_mutable_or_wrong_typed_collections() -> None:
    source, objective, _ = make_objectives()
    capability_descriptor, _ = make_capabilities()

    with pytest.raises(TypeError, match="objective"):
        ObjectiveCapabilityMapping(cast(Any, None), ())
    with pytest.raises(TypeError, match="capabilities"):
        ObjectiveCapabilityMapping(objective, cast(Any, [capability_descriptor]))
    with pytest.raises(TypeError, match="CapabilityDescriptor"):
        ObjectiveCapabilityMapping(objective, cast(Any, (object(),)))
    with pytest.raises(TypeError, match="source_collection"):
        ObjectiveCapabilityMappingCollection(cast(Any, None), ())
    with pytest.raises(TypeError, match="mappings"):
        ObjectiveCapabilityMappingCollection(source, cast(Any, []))
    with pytest.raises(TypeError, match="ObjectiveCapabilityMapping"):
        ObjectiveCapabilityMappingCollection(source, cast(Any, (object(),)))


def test_mapping_rejects_capability_implementation_instances() -> None:
    source, objective, _ = make_objectives()

    class TestCapability(EMSCapabilityBoundary):
        __slots__ = ()

        def evaluate(self, context: Any) -> Any:
            raise AssertionError("mapping must not execute capabilities")

    with pytest.raises(TypeError, match="CapabilityDescriptor"):
        ObjectiveCapabilityMapping(objective, cast(Any, (TestCapability(),)))
    assert source.objectives[0] is objective


def test_models_are_frozen_slotted_and_contain_only_immutable_tuples() -> None:
    source, objective, _ = make_objectives()
    mapping = ObjectiveCapabilityMapping(objective, ())
    collection = ObjectiveCapabilityMappingCollection(source, (mapping,))

    assert [field.name for field in fields(ObjectiveCapabilityMapping)] == [
        "objective",
        "capabilities",
    ]
    assert [field.name for field in fields(ObjectiveCapabilityMappingCollection)] == [
        "source_collection",
        "mappings",
    ]
    assert not hasattr(mapping, "__dict__")
    assert not hasattr(collection, "__dict__")
    assert isinstance(mapping.capabilities, tuple)
    assert isinstance(collection.mappings, tuple)
    with pytest.raises(FrozenInstanceError):
        cast(Any, mapping).capabilities = ()
    with pytest.raises(FrozenInstanceError):
        cast(Any, collection).mappings = ()


def test_mapping_module_has_contract_only_dependencies() -> None:
    source = inspect.getsource(mapping_module)
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "capability.descriptor",
        "dataclasses",
        "objective.activation",
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


def test_no_concrete_production_mapping_boundary_is_introduced() -> None:
    production_boundaries = [
        value
        for value in vars(mapping_module).values()
        if inspect.isclass(value)
        and value.__module__ == mapping_module.__name__
        and issubclass(value, ObjectiveCapabilityMappingBoundary)
    ]

    assert production_boundaries == [ObjectiveCapabilityMappingBoundary]
    assert inspect.isabstract(production_boundaries[0])


def test_public_exports_include_mapping_contracts() -> None:
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
