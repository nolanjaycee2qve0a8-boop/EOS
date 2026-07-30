"""Tests for the EMS intent resolution boundary."""

import ast
import inspect
from abc import ABC
from typing import Any, cast, get_type_hints

import pytest

from capability import IntentResolutionBoundary
from capability import resolution as resolution_module
from kernel.decision import DecisionIntent


class SingleCandidateTestResolution(IntentResolutionBoundary):
    """Test-only implementation without multi-intent resolution semantics."""

    __slots__ = ()

    def resolve(
        self,
        candidates: tuple[DecisionIntent, ...],
    ) -> DecisionIntent:
        if len(candidates) != 1:
            raise ValueError("test resolver requires exactly one candidate")
        return candidates[0]


def test_resolution_boundary_is_abstract() -> None:
    assert issubclass(IntentResolutionBoundary, ABC)
    assert inspect.isabstract(IntentResolutionBoundary)
    with pytest.raises(TypeError):
        IntentResolutionBoundary()  # type: ignore[abstract]


def test_resolve_contract_is_explicit() -> None:
    parameters = list(inspect.signature(IntentResolutionBoundary.resolve).parameters)
    hints = get_type_hints(IntentResolutionBoundary.resolve)

    assert parameters == ["self", "candidates"]
    assert hints == {
        "candidates": tuple[DecisionIntent, ...],
        "return": DecisionIntent,
    }


def test_conforming_boundary_receives_exact_candidate_tuple() -> None:
    intent = DecisionIntent(2.0)
    candidates = (intent,)

    resolved = SingleCandidateTestResolution().resolve(candidates)

    assert resolved is intent


def test_boundary_has_no_instance_state() -> None:
    resolution = SingleCandidateTestResolution()

    assert IntentResolutionBoundary.__slots__ == ()
    assert not hasattr(resolution, "__dict__")
    for forbidden in (
        "candidates",
        "priority",
        "weights",
        "scores",
        "ranking",
        "cache",
        "history",
        "runtime",
    ):
        assert not hasattr(resolution, forbidden)
    with pytest.raises(AttributeError):
        cast(Any, resolution).cache = {}


def test_boundary_module_has_only_stable_contract_dependencies() -> None:
    source = inspect.getsource(resolution_module)
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {"abc", "kernel.decision"}
    for forbidden in (
        "constraint",
        "evaluation",
        "runtime",
        "dispatch",
        "device",
        "persistence",
        "telemetry",
        "optimization",
        "forecast",
        "tou",
    ):
        assert all(
            forbidden not in module for module in imported_modules if module is not None
        )


def test_no_concrete_production_resolution_is_introduced() -> None:
    production_classes = [
        value
        for value in vars(resolution_module).values()
        if inspect.isclass(value) and value.__module__ == resolution_module.__name__
    ]

    assert production_classes == [IntentResolutionBoundary]
    assert inspect.isabstract(production_classes[0])


def test_public_import() -> None:
    from capability import __all__ as public_names

    assert public_names == [
        "CapabilityCompositionBoundary",
        "EMSCapabilityBoundary",
        "IntentResolutionBoundary",
        "SelfConsumptionCapability",
        "TOUCapabilityParameters",
        "TOUEnergyCapability",
    ]
