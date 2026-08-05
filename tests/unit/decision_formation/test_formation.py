"""Tests for the Phase 5 decision formation boundary contracts."""

import ast
import inspect
from abc import ABC
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from typing import Any, cast, get_type_hints

import pytest

from capability import (
    ActiveCapabilityCollection,
    AvailableCapabilityCollection,
    CapabilityDescriptor,
    CapabilityMatch,
    CapabilityMatchCollection,
    RequiredCapabilityCollection,
)
from decision_formation import (
    DecisionFormationBoundary,
    DecisionFormationInput,
    DecisionIntent,
    DecisionIntentCandidate,
)
from decision_formation import boundary as boundary_module
from decision_formation import candidate as candidate_module
from decision_formation import input as input_module
from kernel.decision import DecisionContext
from objective import (
    ObjectiveCapabilityActivationComposition,
    ObjectiveDescriptor,
)


class MinimalDecisionFormationBoundary(DecisionFormationBoundary):
    """Test-only implementation returning one pre-existing candidate."""

    __slots__ = ("_candidate",)

    def __init__(self, candidate: DecisionIntentCandidate) -> None:
        self._candidate = candidate

    def form(
        self,
        formation_input: DecisionFormationInput,
    ) -> DecisionIntentCandidate:
        assert formation_input is self._candidate.formation_input
        return self._candidate


def make_context() -> DecisionContext:
    return DecisionContext(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        soc=0.5,
        battery_power_limit_kw=10.0,
        battery_energy_capacity_kwh=20.0,
        pv_power_kw=5.0,
        load_power_kw=3.0,
        grid_power_kw=-2.0,
        electricity_price_cny_per_kwh=0.5,
        reserve_soc=0.2,
        export_limit_kw=5.0,
    )


def make_composition() -> tuple[
    ObjectiveCapabilityActivationComposition,
    CapabilityDescriptor,
    CapabilityDescriptor,
]:
    objective = ObjectiveDescriptor("cost", "Reduce energy cost.")
    required_active = CapabilityDescriptor("required-active", "Required active.")
    required_inactive = CapabilityDescriptor(
        "required-inactive",
        "Required inactive.",
    )
    available_active = CapabilityDescriptor("available-active", "Available active.")
    available_inactive = CapabilityDescriptor(
        "available-inactive",
        "Available inactive.",
    )
    required = RequiredCapabilityCollection((required_active, required_inactive))
    available = AvailableCapabilityCollection((available_active, available_inactive))
    matches = CapabilityMatchCollection(
        required,
        available,
        (
            CapabilityMatch(required_active, available_active),
            CapabilityMatch(required_inactive, available_inactive),
        ),
        (),
    )
    active = ActiveCapabilityCollection(
        matches,
        (available_active,),
        (available_inactive,),
    )
    composition = ObjectiveCapabilityActivationComposition(objective, active)
    return composition, available_active, available_inactive


def make_formation_input() -> tuple[
    DecisionFormationInput,
    DecisionContext,
    ObjectiveCapabilityActivationComposition,
    CapabilityDescriptor,
]:
    context = make_context()
    composition, capability, _ = make_composition()
    formation_input = DecisionFormationInput(
        source_context=context,
        composition=composition,
        capability=capability,
    )
    return formation_input, context, composition, capability


def test_formation_input_preserves_exact_source_identities() -> None:
    formation_input, context, composition, capability = make_formation_input()

    assert formation_input.source_context is context
    assert formation_input.composition is composition
    assert formation_input.capability is capability
    assert any(
        formation_input.capability is active_capability
        for active_capability in (
            formation_input.composition.active_capabilities.active_capabilities
        )
    )


def test_candidate_preserves_exact_input_and_intent_identities() -> None:
    formation_input, _, _, _ = make_formation_input()
    intent = DecisionIntent("charge")

    candidate = DecisionIntentCandidate(formation_input, intent)

    assert candidate.formation_input is formation_input
    assert candidate.intent is intent


def test_input_rejects_capability_not_in_active_collection() -> None:
    context = make_context()
    composition, _, inactive = make_composition()

    with pytest.raises(ValueError, match="active capability descriptor identity"):
        DecisionFormationInput(context, composition, inactive)


def test_input_rejects_reconstructed_equal_capability_descriptor() -> None:
    context = make_context()
    composition, active, _ = make_composition()
    reconstructed = CapabilityDescriptor(active.name, active.description)

    assert reconstructed == active
    assert reconstructed is not active
    with pytest.raises(ValueError, match="identity"):
        DecisionFormationInput(context, composition, reconstructed)


@pytest.mark.parametrize(
    ("field_name", "value", "error_name"),
    [
        ("source_context", None, "source_context"),
        ("composition", None, "composition"),
        ("capability", None, "capability"),
    ],
)
def test_input_rejects_invalid_field_types(
    field_name: str,
    value: object,
    error_name: str,
) -> None:
    formation_input, context, composition, capability = make_formation_input()
    values: dict[str, object] = {
        "source_context": context,
        "composition": composition,
        "capability": capability,
    }
    values[field_name] = value

    with pytest.raises(TypeError, match=error_name):
        DecisionFormationInput(**cast(Any, values))
    assert formation_input.source_context is context


def test_candidate_rejects_invalid_field_types() -> None:
    formation_input, _, _, _ = make_formation_input()
    intent = DecisionIntent("idle")

    with pytest.raises(TypeError, match="formation_input"):
        DecisionIntentCandidate(cast(Any, None), intent)
    with pytest.raises(TypeError, match="intent"):
        DecisionIntentCandidate(formation_input, cast(Any, None))


def test_models_are_frozen_slotted_and_field_complete() -> None:
    formation_input, _, _, _ = make_formation_input()
    candidate = DecisionIntentCandidate(formation_input, DecisionIntent("idle"))

    assert [field.name for field in fields(DecisionFormationInput)] == [
        "source_context",
        "composition",
        "capability",
    ]
    assert DecisionFormationInput.__slots__ == (
        "source_context",
        "composition",
        "capability",
    )
    assert [field.name for field in fields(DecisionIntentCandidate)] == [
        "formation_input",
        "intent",
    ]
    assert DecisionIntentCandidate.__slots__ == ("formation_input", "intent")
    assert not hasattr(formation_input, "__dict__")
    assert not hasattr(candidate, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, formation_input).capability = formation_input.capability
    with pytest.raises(FrozenInstanceError):
        cast(Any, candidate).intent = candidate.intent


def test_boundary_is_abstract_stateless_and_empty_slotted() -> None:
    assert issubclass(DecisionFormationBoundary, ABC)
    assert inspect.isabstract(DecisionFormationBoundary)
    assert DecisionFormationBoundary.__slots__ == ()
    with pytest.raises(TypeError):
        DecisionFormationBoundary()  # type: ignore[abstract]


def test_boundary_signature_is_exact() -> None:
    parameters = list(inspect.signature(DecisionFormationBoundary.form).parameters)
    hints = get_type_hints(DecisionFormationBoundary.form)

    assert parameters == ["self", "formation_input"]
    assert hints == {
        "formation_input": DecisionFormationInput,
        "return": DecisionIntentCandidate,
    }


def test_test_only_boundary_returns_exact_candidate() -> None:
    formation_input, _, _, _ = make_formation_input()
    candidate = DecisionIntentCandidate(formation_input, DecisionIntent("idle"))
    boundary = MinimalDecisionFormationBoundary(candidate)

    result = boundary.form(formation_input)

    assert result is candidate


def test_production_modules_have_contract_only_dependencies() -> None:
    modules = {
        input_module: {
            "capability.descriptor",
            "dataclasses",
            "kernel.decision.context",
            "objective.activation_composition",
        },
        candidate_module: {
            "dataclasses",
            "decision_formation.input",
            "decision_formation.intent",
        },
        boundary_module: {
            "abc",
            "decision_formation.candidate",
            "decision_formation.input",
        },
    }
    for module, expected_imports in modules.items():
        source = inspect.getsource(module)
        tree = ast.parse(source)
        imported_modules = {
            node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        }
        assert imported_modules == expected_imports


def test_no_concrete_production_formation_boundary_exists() -> None:
    production_boundaries = [
        value
        for value in vars(boundary_module).values()
        if inspect.isclass(value)
        and value.__module__ == boundary_module.__name__
        and issubclass(value, DecisionFormationBoundary)
    ]

    assert production_boundaries == [DecisionFormationBoundary]
    assert inspect.isabstract(production_boundaries[0])


def test_boundary_has_no_forbidden_behavior_or_state() -> None:
    for forbidden in (
        "charge",
        "discharge",
        "select",
        "optimize",
        "constraint",
        "command",
        "runtime",
        "device",
        "cache",
        "history",
    ):
        assert not hasattr(DecisionFormationBoundary, forbidden)
