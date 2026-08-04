"""Tests for immutable capability activation contracts."""

import ast
import inspect
from abc import ABC
from dataclasses import FrozenInstanceError, fields
from typing import Any, cast, get_type_hints

import pytest

from capability import (
    ActiveCapabilityCollection,
    AvailableCapabilityCollection,
    CapabilityActivationBoundary,
    CapabilityDescriptor,
    CapabilityMatch,
    CapabilityMatchCollection,
    RequiredCapabilityCollection,
)
from capability import activation as activation_module


class RecordingActivation(CapabilityActivationBoundary):
    """Test-only activation with caller-visible exactly-once evidence."""

    __slots__ = ("calls",)

    def __init__(self) -> None:
        self.calls = 0

    def activate(
        self,
        matches: CapabilityMatchCollection,
    ) -> ActiveCapabilityCollection:
        self.calls += 1
        active = tuple(match.available for match in matches.matches)
        return ActiveCapabilityCollection(matches, active, ())


def make_matches() -> tuple[
    CapabilityMatchCollection,
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
    return (
        CapabilityMatchCollection(required, available, matches, ()),
        available_first,
        available_second,
    )


def test_activation_boundary_is_abstract_and_stateless() -> None:
    assert issubclass(CapabilityActivationBoundary, ABC)
    assert inspect.isabstract(CapabilityActivationBoundary)
    assert CapabilityActivationBoundary.__slots__ == ()
    with pytest.raises(TypeError):
        CapabilityActivationBoundary()  # type: ignore[abstract]


def test_activate_contract_accepts_exact_match_collection() -> None:
    parameters = list(
        inspect.signature(CapabilityActivationBoundary.activate).parameters
    )
    hints = get_type_hints(CapabilityActivationBoundary.activate)

    assert parameters == ["self", "matches"]
    assert hints == {
        "matches": CapabilityMatchCollection,
        "return": ActiveCapabilityCollection,
    }


def test_activation_executes_once_and_preserves_source_identity() -> None:
    source, first, second = make_matches()
    activation = RecordingActivation()

    result = activation.activate(source)

    assert activation.calls == 1
    assert result.source_collection is source
    assert result.active_capabilities[0] is first
    assert result.active_capabilities[1] is second
    assert result.inactive_capabilities == ()


def test_active_and_inactive_states_preserve_exact_identities_and_order() -> None:
    source, first, second = make_matches()
    active = (second,)
    inactive = (first,)

    result = ActiveCapabilityCollection(source, active, inactive)

    assert result.source_collection is source
    assert result.active_capabilities is active
    assert result.active_capabilities[0] is second
    assert result.inactive_capabilities is inactive
    assert result.inactive_capabilities[0] is first


def test_empty_matched_result_has_empty_activation_states() -> None:
    required = RequiredCapabilityCollection(())
    available = AvailableCapabilityCollection(())
    source = CapabilityMatchCollection(required, available, (), ())
    active: tuple[CapabilityDescriptor, ...] = ()
    inactive: tuple[CapabilityDescriptor, ...] = ()

    result = ActiveCapabilityCollection(source, active, inactive)

    assert result.active_capabilities is active
    assert result.inactive_capabilities is inactive


def test_activation_collection_rejects_invalid_types() -> None:
    source, first, second = make_matches()

    with pytest.raises(TypeError, match="source_collection"):
        ActiveCapabilityCollection(cast(Any, None), (), ())
    with pytest.raises(TypeError, match="active_capabilities"):
        ActiveCapabilityCollection(source, cast(Any, [first]), (second,))
    with pytest.raises(TypeError, match="inactive_capabilities"):
        ActiveCapabilityCollection(source, (first,), cast(Any, [second]))
    with pytest.raises(TypeError, match="CapabilityDescriptor"):
        ActiveCapabilityCollection(source, cast(Any, (object(),)), (first, second))


def test_activation_collection_rejects_nonmatched_or_reconstructed_descriptor() -> None:
    source, first, second = make_matches()
    reconstructed = CapabilityDescriptor(first.name, first.description)
    unrelated = CapabilityDescriptor("unrelated", "Not part of the matched result.")

    assert reconstructed == first
    assert reconstructed is not first
    with pytest.raises(ValueError, match="identity"):
        ActiveCapabilityCollection(source, (reconstructed,), (first, second))
    with pytest.raises(ValueError, match="identity"):
        ActiveCapabilityCollection(source, (first,), (second, unrelated))


def test_every_matched_descriptor_must_have_exactly_one_state() -> None:
    source, first, second = make_matches()

    with pytest.raises(ValueError, match="exactly one"):
        ActiveCapabilityCollection(source, (first,), ())
    with pytest.raises(ValueError, match="exactly one"):
        ActiveCapabilityCollection(source, (first, second), (second,))


def test_activation_collection_is_frozen_slotted_and_tuple_only() -> None:
    source, first, second = make_matches()
    result = ActiveCapabilityCollection(source, (first,), (second,))

    assert [field.name for field in fields(ActiveCapabilityCollection)] == [
        "source_collection",
        "active_capabilities",
        "inactive_capabilities",
    ]
    assert ActiveCapabilityCollection.__slots__ == (
        "source_collection",
        "active_capabilities",
        "inactive_capabilities",
    )
    assert not hasattr(result, "__dict__")
    assert isinstance(result.active_capabilities, tuple)
    assert isinstance(result.inactive_capabilities, tuple)
    with pytest.raises(FrozenInstanceError):
        cast(Any, result).active_capabilities = ()


def test_activation_module_has_contract_only_dependencies() -> None:
    source = inspect.getsource(activation_module)
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "capability.descriptor",
        "capability.matching",
        "dataclasses",
    }


def test_no_concrete_production_activation_is_introduced() -> None:
    production_boundaries = [
        value
        for value in vars(activation_module).values()
        if inspect.isclass(value)
        and value.__module__ == activation_module.__name__
        and issubclass(value, CapabilityActivationBoundary)
    ]

    assert production_boundaries == [CapabilityActivationBoundary]
    assert inspect.isabstract(production_boundaries[0])


def test_boundary_has_no_selection_execution_or_intent_contract() -> None:
    for forbidden in (
        "priority",
        "rank",
        "score",
        "select",
        "optimize",
        "resolve",
        "fallback",
        "evaluate",
        "intent",
        "constraint",
        "device",
        "runtime",
        "cache",
        "history",
    ):
        assert not hasattr(CapabilityActivationBoundary, forbidden)


def test_public_exports_include_activation_contracts() -> None:
    from capability import __all__ as public_names

    assert "ActiveCapabilityCollection" in public_names
    assert "CapabilityActivationBoundary" in public_names
