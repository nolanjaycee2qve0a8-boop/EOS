"""Tests for immutable capability matching contracts."""

import ast
import inspect
from abc import ABC
from dataclasses import FrozenInstanceError, fields
from typing import Any, cast, get_type_hints

import pytest

from capability import (
    AvailableCapabilityCollection,
    CapabilityDescriptor,
    CapabilityMatch,
    CapabilityMatchCollection,
    CapabilityMatchingBoundary,
    RequiredCapabilityCollection,
)
from capability import matching as matching_module


def make_descriptors() -> tuple[
    CapabilityDescriptor,
    CapabilityDescriptor,
    CapabilityDescriptor,
    CapabilityDescriptor,
]:
    required_first = CapabilityDescriptor("required-first", "First requirement.")
    required_second = CapabilityDescriptor("required-second", "Second requirement.")
    available_first = CapabilityDescriptor("available-first", "First availability.")
    available_second = CapabilityDescriptor("available-second", "Second availability.")
    return required_first, required_second, available_first, available_second


def test_matching_boundary_is_abstract_and_stateless() -> None:
    assert issubclass(CapabilityMatchingBoundary, ABC)
    assert inspect.isabstract(CapabilityMatchingBoundary)
    assert CapabilityMatchingBoundary.__slots__ == ()
    with pytest.raises(TypeError):
        CapabilityMatchingBoundary()  # type: ignore[abstract]


def test_matching_boundary_signature_uses_immutable_collections() -> None:
    parameters = list(
        inspect.signature(CapabilityMatchingBoundary.match_capabilities).parameters
    )
    hints = get_type_hints(CapabilityMatchingBoundary.match_capabilities)

    assert parameters == ["self", "required", "available"]
    assert hints == {
        "required": RequiredCapabilityCollection,
        "available": AvailableCapabilityCollection,
        "return": CapabilityMatchCollection,
    }


def test_required_collection_preserves_tuple_and_descriptor_identities() -> None:
    required_first, required_second, _, _ = make_descriptors()
    descriptors = (required_first, required_second)

    required = RequiredCapabilityCollection(descriptors)

    assert required.capabilities is descriptors
    assert required.capabilities[0] is required_first
    assert required.capabilities[1] is required_second


def test_empty_required_collection_preserves_exact_empty_tuple() -> None:
    descriptors: tuple[CapabilityDescriptor, ...] = ()

    required = RequiredCapabilityCollection(descriptors)

    assert required.capabilities is descriptors


def test_match_preserves_required_and_available_descriptor_identities() -> None:
    required_descriptor, _, available_descriptor, _ = make_descriptors()

    capability_match = CapabilityMatch(required_descriptor, available_descriptor)

    assert capability_match.required is required_descriptor
    assert capability_match.available is available_descriptor


def test_all_matched_preserves_all_source_and_match_identities() -> None:
    required_first, required_second, available_first, available_second = (
        make_descriptors()
    )
    required = RequiredCapabilityCollection((required_first, required_second))
    available = AvailableCapabilityCollection((available_first, available_second))
    first_match = CapabilityMatch(required_first, available_second)
    second_match = CapabilityMatch(required_second, available_first)
    matches = (first_match, second_match)

    missing_required: tuple[CapabilityDescriptor, ...] = ()
    collection = CapabilityMatchCollection(
        required, available, matches, missing_required
    )

    assert collection.required_collection is required
    assert collection.available_collection is available
    assert collection.matches is matches
    assert collection.matches[0] is first_match
    assert collection.matches[1] is second_match
    assert collection.missing_required is missing_required


def test_empty_match_collection_is_valid() -> None:
    required = RequiredCapabilityCollection(())
    available = AvailableCapabilityCollection(())
    matches: tuple[CapabilityMatch, ...] = ()

    missing_required: tuple[CapabilityDescriptor, ...] = ()
    collection = CapabilityMatchCollection(
        required, available, matches, missing_required
    )

    assert collection.matches is matches
    assert collection.missing_required is missing_required


def test_partially_matched_explicitly_preserves_missing_identity() -> None:
    required_first, required_second, available_first, _ = make_descriptors()
    required = RequiredCapabilityCollection((required_first, required_second))
    available = AvailableCapabilityCollection((available_first,))
    matches = (CapabilityMatch(required_first, available_first),)
    missing_required = (required_second,)

    collection = CapabilityMatchCollection(
        required, available, matches, missing_required
    )

    assert collection.matches is matches
    assert collection.matches[0].required is required_first
    assert collection.missing_required is missing_required
    assert collection.missing_required[0] is required_second


def test_fully_missing_explicitly_preserves_all_required_identities() -> None:
    required_first, required_second, _, _ = make_descriptors()
    required = RequiredCapabilityCollection((required_first, required_second))
    available = AvailableCapabilityCollection(())
    matches: tuple[CapabilityMatch, ...] = ()
    missing_required = (required_first, required_second)

    collection = CapabilityMatchCollection(
        required, available, matches, missing_required
    )

    assert collection.matches is matches
    assert collection.missing_required is missing_required
    assert collection.missing_required[0] is required_first
    assert collection.missing_required[1] is required_second


def test_models_reject_mutable_or_wrong_typed_values() -> None:
    required_descriptor, _, available_descriptor, _ = make_descriptors()
    required = RequiredCapabilityCollection((required_descriptor,))
    available = AvailableCapabilityCollection((available_descriptor,))
    capability_match = CapabilityMatch(required_descriptor, available_descriptor)

    with pytest.raises(TypeError, match="capabilities"):
        RequiredCapabilityCollection(cast(Any, [required_descriptor]))
    with pytest.raises(TypeError, match="CapabilityDescriptor"):
        RequiredCapabilityCollection(cast(Any, (object(),)))
    with pytest.raises(TypeError, match="required"):
        CapabilityMatch(cast(Any, None), available_descriptor)
    with pytest.raises(TypeError, match="available"):
        CapabilityMatch(required_descriptor, cast(Any, None))
    with pytest.raises(TypeError, match="required_collection"):
        CapabilityMatchCollection(cast(Any, None), available, (), ())
    with pytest.raises(TypeError, match="available_collection"):
        CapabilityMatchCollection(required, cast(Any, None), (), ())
    with pytest.raises(TypeError, match="matches"):
        CapabilityMatchCollection(
            required, available, cast(Any, [capability_match]), ()
        )
    with pytest.raises(TypeError, match="CapabilityMatch"):
        CapabilityMatchCollection(required, available, cast(Any, (object(),)), ())
    with pytest.raises(TypeError, match="missing_required"):
        CapabilityMatchCollection(
            required, available, (capability_match,), cast(Any, [])
        )
    with pytest.raises(TypeError, match="CapabilityDescriptor"):
        CapabilityMatchCollection(
            required, available, (capability_match,), cast(Any, (object(),))
        )


def test_collection_rejects_descriptors_outside_exact_sources() -> None:
    required_descriptor, _, available_descriptor, _ = make_descriptors()
    required = RequiredCapabilityCollection((required_descriptor,))
    available = AvailableCapabilityCollection((available_descriptor,))
    reconstructed_required = CapabilityDescriptor(
        required_descriptor.name, required_descriptor.description
    )
    reconstructed_available = CapabilityDescriptor(
        available_descriptor.name, available_descriptor.description
    )

    assert reconstructed_required == required_descriptor
    assert reconstructed_required is not required_descriptor
    with pytest.raises(ValueError, match="required identity"):
        CapabilityMatchCollection(
            required,
            available,
            (CapabilityMatch(reconstructed_required, available_descriptor),),
            (),
        )
    with pytest.raises(ValueError, match="available identity"):
        CapabilityMatchCollection(
            required,
            available,
            (CapabilityMatch(required_descriptor, reconstructed_available),),
            (),
        )

    with pytest.raises(ValueError, match="missing_required"):
        CapabilityMatchCollection(
            required,
            available,
            (CapabilityMatch(required_descriptor, available_descriptor),),
            (reconstructed_required,),
        )


def test_required_descriptor_cannot_be_omitted() -> None:
    required_first, required_second, available_first, _ = make_descriptors()
    required = RequiredCapabilityCollection((required_first, required_second))
    available = AvailableCapabilityCollection((available_first,))
    matches = (CapabilityMatch(required_first, available_first),)

    with pytest.raises(ValueError, match="exactly one"):
        CapabilityMatchCollection(required, available, matches, ())


def test_required_descriptor_cannot_be_both_matched_and_missing() -> None:
    required_descriptor, _, available_descriptor, _ = make_descriptors()
    required = RequiredCapabilityCollection((required_descriptor,))
    available = AvailableCapabilityCollection((available_descriptor,))
    matches = (CapabilityMatch(required_descriptor, available_descriptor),)

    with pytest.raises(ValueError, match="exactly one"):
        CapabilityMatchCollection(required, available, matches, (required_descriptor,))


def test_models_are_frozen_slotted_and_tuple_only() -> None:
    required_descriptor, _, available_descriptor, _ = make_descriptors()
    required = RequiredCapabilityCollection((required_descriptor,))
    available = AvailableCapabilityCollection((available_descriptor,))
    capability_match = CapabilityMatch(required_descriptor, available_descriptor)
    collection = CapabilityMatchCollection(required, available, (capability_match,), ())

    assert [field.name for field in fields(RequiredCapabilityCollection)] == [
        "capabilities"
    ]
    assert [field.name for field in fields(CapabilityMatch)] == [
        "required",
        "available",
    ]
    assert [field.name for field in fields(CapabilityMatchCollection)] == [
        "required_collection",
        "available_collection",
        "matches",
        "missing_required",
    ]
    assert RequiredCapabilityCollection.__slots__ == ("capabilities",)
    assert CapabilityMatch.__slots__ == ("required", "available")
    assert CapabilityMatchCollection.__slots__ == (
        "required_collection",
        "available_collection",
        "matches",
        "missing_required",
    )
    for model in (required, capability_match, collection):
        assert not hasattr(model, "__dict__")
    assert isinstance(required.capabilities, tuple)
    assert isinstance(collection.matches, tuple)
    assert isinstance(collection.missing_required, tuple)
    with pytest.raises(FrozenInstanceError):
        cast(Any, collection).matches = ()


def test_matching_module_has_contract_only_dependencies() -> None:
    source = inspect.getsource(matching_module)
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "capability.descriptor",
        "capability.discovery",
        "dataclasses",
    }


def test_no_concrete_matching_or_capability_instance_is_introduced() -> None:
    production_boundaries = [
        value
        for value in vars(matching_module).values()
        if inspect.isclass(value)
        and value.__module__ == matching_module.__name__
        and issubclass(value, CapabilityMatchingBoundary)
    ]

    assert production_boundaries == [CapabilityMatchingBoundary]
    assert inspect.isabstract(production_boundaries[0])


def test_boundary_has_no_selection_activation_or_intent_contract() -> None:
    for forbidden in (
        "rank",
        "score",
        "prioritize",
        "select",
        "optimize",
        "fallback",
        "activate",
        "evaluate",
        "intent",
        "device",
        "runtime",
        "cache",
        "history",
    ):
        assert not hasattr(CapabilityMatchingBoundary, forbidden)


def test_public_exports_include_matching_contracts() -> None:
    from capability import __all__ as public_names

    assert public_names == [
        "ActiveCapabilityCollection",
        "AvailableCapabilityCollection",
        "CapabilityActivationBoundary",
        "CapabilityCompositionBoundary",
        "CapabilityDescriptor",
        "CapabilityDiscoveryBoundary",
        "CapabilityMatch",
        "CapabilityMatchCollection",
        "CapabilityMatchingBoundary",
        "DeterministicIntentResolutionImplementation",
        "DeterministicIntentResolutionParameters",
        "EMSCapabilityBoundary",
        "IntentResolutionBoundary",
        "RequiredCapabilityCollection",
        "SelfConsumptionCapability",
        "TOUCapabilityParameters",
        "TOUEnergyCapability",
    ]
