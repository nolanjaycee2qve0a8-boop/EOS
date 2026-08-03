"""Tests for deterministic caller-parameterized intent resolution."""

import ast
import inspect
from dataclasses import FrozenInstanceError, fields
from typing import Any, cast, get_type_hints

import pytest

from capability import (
    DeterministicIntentResolutionImplementation,
    DeterministicIntentResolutionParameters,
    IntentResolutionBoundary,
)
from capability import deterministic_resolution as resolution_module
from kernel.decision import DecisionIntent


def test_implementation_preserves_resolution_boundary_contract() -> None:
    assert issubclass(
        DeterministicIntentResolutionImplementation,
        IntentResolutionBoundary,
    )
    assert not inspect.isabstract(DeterministicIntentResolutionImplementation)
    assert get_type_hints(DeterministicIntentResolutionImplementation.resolve) == {
        "candidates": tuple[DecisionIntent, ...],
        "return": DecisionIntent,
    }


@pytest.mark.parametrize("selected_candidate_index", [0, 1, 2])
def test_explicit_index_returns_exact_candidate_identity(
    selected_candidate_index: int,
) -> None:
    candidates = (
        DecisionIntent(3.0),
        DecisionIntent(-2.0),
        DecisionIntent(0.0),
    )
    resolver = DeterministicIntentResolutionImplementation(
        DeterministicIntentResolutionParameters(
            selected_candidate_index=selected_candidate_index,
        )
    )

    resolved = resolver.resolve(candidates)

    assert resolved is candidates[selected_candidate_index]


def test_caller_tuple_order_is_not_modified() -> None:
    first = DecisionIntent(1.0)
    second = DecisionIntent(2.0)
    candidates = (second, first)
    resolver = DeterministicIntentResolutionImplementation(
        DeterministicIntentResolutionParameters(selected_candidate_index=0)
    )

    resolved = resolver.resolve(candidates)

    assert candidates == (second, first)
    assert resolved is second


def test_duplicate_candidate_positions_remain_distinct_positions() -> None:
    intent = DecisionIntent(1.0)
    candidates = (intent, intent)
    resolver = DeterministicIntentResolutionImplementation(
        DeterministicIntentResolutionParameters(selected_candidate_index=1)
    )

    resolved = resolver.resolve(candidates)

    assert resolved is candidates[1]
    assert resolved is intent


@pytest.mark.parametrize("invalid_index", [True, 1.0, "1", None])
def test_selected_candidate_index_requires_int(invalid_index: object) -> None:
    with pytest.raises(TypeError, match="selected_candidate_index"):
        DeterministicIntentResolutionParameters(
            selected_candidate_index=cast(int, invalid_index),
        )


def test_selected_candidate_index_must_be_non_negative() -> None:
    with pytest.raises(ValueError, match="selected_candidate_index"):
        DeterministicIntentResolutionParameters(selected_candidate_index=-1)


@pytest.mark.parametrize(
    "candidates",
    [
        (),
        (DecisionIntent(1.0),),
    ],
)
def test_selected_candidate_index_must_exist(
    candidates: tuple[DecisionIntent, ...],
) -> None:
    resolver = DeterministicIntentResolutionImplementation(
        DeterministicIntentResolutionParameters(selected_candidate_index=1)
    )

    with pytest.raises(ValueError, match="selected_candidate_index"):
        resolver.resolve(candidates)


def test_candidates_must_be_tuple_of_intents() -> None:
    resolver = DeterministicIntentResolutionImplementation(
        DeterministicIntentResolutionParameters(selected_candidate_index=0)
    )

    with pytest.raises(TypeError, match="candidates"):
        resolver.resolve(cast(tuple[DecisionIntent, ...], [DecisionIntent(1.0)]))
    with pytest.raises(TypeError, match="candidates"):
        resolver.resolve(cast(tuple[DecisionIntent, ...], (object(),)))


def test_parameters_and_implementation_are_frozen_and_slotted() -> None:
    parameters = DeterministicIntentResolutionParameters(
        selected_candidate_index=0,
    )
    resolver = DeterministicIntentResolutionImplementation(parameters)

    assert tuple(
        field.name for field in fields(DeterministicIntentResolutionParameters)
    ) == ("selected_candidate_index",)
    assert tuple(
        field.name for field in fields(DeterministicIntentResolutionImplementation)
    ) == ("parameters",)
    assert resolver.parameters is parameters
    assert not hasattr(parameters, "__dict__")
    assert not hasattr(resolver, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, parameters).selected_candidate_index = 1
    with pytest.raises(FrozenInstanceError):
        cast(Any, resolver).parameters = parameters


def test_invalid_parameters_raise_type_error() -> None:
    with pytest.raises(TypeError, match="parameters"):
        DeterministicIntentResolutionImplementation(
            cast(DeterministicIntentResolutionParameters, object())
        )


def test_resolver_has_no_runtime_state() -> None:
    resolver = DeterministicIntentResolutionImplementation(
        DeterministicIntentResolutionParameters(selected_candidate_index=0)
    )

    for forbidden in (
        "capability_name",
        "priority",
        "weights",
        "scores",
        "ranking",
        "cache",
        "history",
        "runtime",
        "dispatcher",
        "device",
    ):
        assert not hasattr(resolver, forbidden)


def test_module_has_no_forbidden_dependencies_or_special_cases() -> None:
    source = inspect.getsource(resolution_module)
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "capability.resolution",
        "dataclasses",
        "kernel.decision",
    }
    assert "TOU" not in source
    assert "SelfConsumption" not in source
    for forbidden in (
        "constraint",
        "runtime",
        "dispatch",
        "device",
        "persistence",
        "telemetry",
        "optimization",
        "forecast",
    ):
        assert all(
            forbidden not in module for module in imported_modules if module is not None
        )


def test_public_imports() -> None:
    from capability import __all__ as public_names

    assert public_names == [
        "CapabilityCompositionBoundary",
        "CapabilityDescriptor",
        "DeterministicIntentResolutionImplementation",
        "DeterministicIntentResolutionParameters",
        "EMSCapabilityBoundary",
        "IntentResolutionBoundary",
        "SelfConsumptionCapability",
        "TOUCapabilityParameters",
        "TOUEnergyCapability",
    ]
