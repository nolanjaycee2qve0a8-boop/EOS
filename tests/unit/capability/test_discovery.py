"""Tests for immutable capability discovery contracts."""

import ast
import inspect
from abc import ABC
from dataclasses import FrozenInstanceError, fields
from typing import Any, cast, get_type_hints

import pytest

from capability import (
    AvailableCapabilityCollection,
    CapabilityDescriptor,
    CapabilityDiscoveryBoundary,
)
from capability import discovery as discovery_module


def make_descriptors() -> tuple[CapabilityDescriptor, CapabilityDescriptor]:
    first = CapabilityDescriptor("first", "First test-only capability.")
    second = CapabilityDescriptor("second", "Second test-only capability.")
    return first, second


def test_discovery_boundary_is_abstract_and_stateless() -> None:
    assert issubclass(CapabilityDiscoveryBoundary, ABC)
    assert inspect.isabstract(CapabilityDiscoveryBoundary)
    assert CapabilityDiscoveryBoundary.__slots__ == ()
    with pytest.raises(TypeError):
        CapabilityDiscoveryBoundary()  # type: ignore[abstract]


def test_discover_contract_returns_available_descriptor_collection() -> None:
    parameters = list(
        inspect.signature(CapabilityDiscoveryBoundary.discover).parameters
    )
    hints = get_type_hints(CapabilityDiscoveryBoundary.discover)

    assert parameters == ["self"]
    assert hints == {"return": AvailableCapabilityCollection}


def test_available_collection_preserves_tuple_and_descriptor_identities() -> None:
    first, second = make_descriptors()
    descriptors = (first, second)

    available = AvailableCapabilityCollection(descriptors)

    assert available.capabilities is descriptors
    assert available.capabilities[0] is first
    assert available.capabilities[1] is second


def test_empty_available_collection_preserves_exact_empty_tuple() -> None:
    descriptors: tuple[CapabilityDescriptor, ...] = ()

    available = AvailableCapabilityCollection(descriptors)

    assert available.capabilities is descriptors


def test_available_collection_rejects_mutable_or_invalid_values() -> None:
    first, _ = make_descriptors()

    with pytest.raises(TypeError, match="capabilities"):
        AvailableCapabilityCollection(cast(Any, [first]))
    with pytest.raises(TypeError, match="CapabilityDescriptor"):
        AvailableCapabilityCollection(cast(Any, (object(),)))


def test_available_collection_is_frozen_slotted_and_deeply_immutable() -> None:
    first, _ = make_descriptors()
    available = AvailableCapabilityCollection((first,))

    assert [field.name for field in fields(AvailableCapabilityCollection)] == [
        "capabilities"
    ]
    assert AvailableCapabilityCollection.__slots__ == ("capabilities",)
    assert not hasattr(available, "__dict__")
    assert isinstance(available.capabilities, tuple)
    with pytest.raises(FrozenInstanceError):
        cast(Any, available).capabilities = ()


def test_discovery_module_has_descriptor_only_dependencies() -> None:
    source = inspect.getsource(discovery_module)
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {"abc", "capability.descriptor", "dataclasses"}


def test_no_concrete_discovery_or_capability_instance_is_introduced() -> None:
    production_boundaries = [
        value
        for value in vars(discovery_module).values()
        if inspect.isclass(value)
        and value.__module__ == discovery_module.__name__
        and issubclass(value, CapabilityDiscoveryBoundary)
    ]

    assert production_boundaries == [CapabilityDiscoveryBoundary]
    assert inspect.isabstract(production_boundaries[0])


def test_boundary_contains_no_matching_selection_activation_or_intent_contract() -> (
    None
):
    for forbidden in (
        "match",
        "select",
        "activate",
        "evaluate",
        "intent",
        "device",
        "cache",
        "history",
        "runtime",
    ):
        assert not hasattr(CapabilityDiscoveryBoundary, forbidden)


def test_public_exports_include_discovery_contracts() -> None:
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
