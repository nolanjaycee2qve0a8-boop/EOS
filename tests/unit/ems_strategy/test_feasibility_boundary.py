"""Tests for the EMS decision feasibility architecture seam."""

import ast
import inspect
from abc import ABC
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast, get_type_hints

import pytest

import ems_strategy
from capability import (
    ActiveCapabilityCollection,
    AvailableCapabilityCollection,
    CapabilityDescriptor,
    CapabilityMatch,
    CapabilityMatchCollection,
    RequiredCapabilityCollection,
)
from decision_formation import DecisionIntent
from ems_strategy import (
    DecisionProvenance,
    EMSContext,
    EMSDecision,
    EMSStrategyDescriptor,
    FeasibilityBoundary,
    FeasibleDecision,
)
from kernel.decision import DecisionContext
from objective import (
    ObjectiveCapabilityActivationComposition,
    ObjectiveDescriptor,
)


class PassThroughFeasibility(FeasibilityBoundary):
    """Test-only feasibility implementation with no constraint algorithm."""

    __slots__ = ()

    def evaluate(
        self,
        decision: EMSDecision,
        *,
        provenance: DecisionProvenance,
    ) -> FeasibleDecision:
        if not isinstance(decision, EMSDecision):
            raise TypeError("decision must be an EMSDecision")
        if not isinstance(provenance, DecisionProvenance):
            raise TypeError("provenance must be a DecisionProvenance")
        return FeasibleDecision(
            decision,
            provenance,
            decision.intent,
            decision.requested_power_kw,
        )


def make_decision() -> tuple[EMSDecision, DecisionProvenance]:
    source_context = DecisionContext(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        soc=0.5,
        battery_power_limit_kw=3.0,
        battery_energy_capacity_kwh=10.0,
        pv_power_kw=4.0,
        load_power_kw=1.0,
        grid_power_kw=0.0,
        electricity_price_cny_per_kwh=0.5,
        reserve_soc=0.2,
        export_limit_kw=5.0,
    )
    required = CapabilityDescriptor("test", "Required test capability.")
    available = CapabilityDescriptor("test", "Available test capability.")
    required_collection = RequiredCapabilityCollection((required,))
    available_collection = AvailableCapabilityCollection((available,))
    matches = CapabilityMatchCollection(
        required_collection,
        available_collection,
        (CapabilityMatch(required, available),),
        (),
    )
    active = ActiveCapabilityCollection(matches, (available,), ())
    composition = ObjectiveCapabilityActivationComposition(
        ObjectiveDescriptor("test", "Test objective."),
        active,
    )
    context = EMSContext(source_context, composition, available)
    strategy = EMSStrategyDescriptor("test-strategy", "1.0")
    decision = EMSDecision(context, strategy, DecisionIntent("charge"), 2.0)
    provenance = DecisionProvenance(context, strategy, decision)
    return decision, provenance


def test_boundary_is_abstract_and_cannot_be_instantiated() -> None:
    assert issubclass(FeasibilityBoundary, ABC)
    assert inspect.isabstract(FeasibilityBoundary)
    assert getattr(FeasibilityBoundary.evaluate, "__isabstractmethod__", False)
    with pytest.raises(TypeError):
        FeasibilityBoundary()  # type: ignore[abstract]


def test_boundary_signature_preserves_explicit_provenance() -> None:
    signature = inspect.signature(FeasibilityBoundary.evaluate)
    hints = get_type_hints(FeasibilityBoundary.evaluate)

    assert list(signature.parameters) == ["self", "decision", "provenance"]
    assert signature.parameters["provenance"].kind is inspect.Parameter.KEYWORD_ONLY
    assert hints == {
        "decision": EMSDecision,
        "provenance": DecisionProvenance,
        "return": FeasibleDecision,
    }


def test_minimal_fake_implementation_returns_feasible_decision() -> None:
    decision, provenance = make_decision()

    feasible = PassThroughFeasibility().evaluate(
        decision,
        provenance=provenance,
    )

    assert isinstance(feasible, FeasibleDecision)
    assert feasible.source_decision is decision
    assert feasible.source_provenance is provenance
    assert feasible.approved_intent is decision.intent
    assert feasible.approved_power_kw == decision.requested_power_kw


def test_feasible_decision_is_frozen_slotted_and_has_no_mutable_fields() -> None:
    decision, provenance = make_decision()
    feasible = FeasibleDecision(
        decision,
        provenance,
        decision.intent,
        decision.requested_power_kw,
    )

    assert [field.name for field in fields(FeasibleDecision)] == [
        "source_decision",
        "source_provenance",
        "approved_intent",
        "approved_power_kw",
    ]
    assert FeasibleDecision.__slots__ == (
        "source_decision",
        "source_provenance",
        "approved_intent",
        "approved_power_kw",
    )
    assert not hasattr(feasible, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, feasible).approved_power_kw = 1.0


def test_reconstructed_equal_decision_is_rejected_by_provenance_identity() -> None:
    decision, provenance = make_decision()
    reconstructed = EMSDecision(
        decision.source_context,
        decision.source_strategy,
        decision.intent,
        decision.requested_power_kw,
    )

    assert reconstructed == decision
    assert reconstructed is not decision
    with pytest.raises(ValueError, match="source_decision identity"):
        FeasibleDecision(
            reconstructed,
            provenance,
            reconstructed.intent,
            reconstructed.requested_power_kw,
        )


def test_feasibility_may_reduce_source_action_to_idle() -> None:
    decision, provenance = make_decision()
    idle = DecisionIntent("idle")

    feasible = FeasibleDecision(decision, provenance, idle, 0.0)

    assert feasible.source_decision is decision
    assert feasible.approved_intent is idle
    assert feasible.approved_power_kw == 0.0


def test_feasibility_must_not_reverse_source_action() -> None:
    decision, provenance = make_decision()

    with pytest.raises(ValueError, match="must not reverse"):
        FeasibleDecision(
            decision,
            provenance,
            DecisionIntent("discharge"),
            1.0,
        )


@pytest.mark.parametrize(
    ("intent", "power"),
    [
        (DecisionIntent("idle"), 1.0),
        (DecisionIntent("charge"), 0.0),
        (DecisionIntent("charge"), -1.0),
        (DecisionIntent("charge"), float("inf")),
    ],
)
def test_feasible_decision_rejects_invalid_approved_power_contract(
    intent: DecisionIntent,
    power: float,
) -> None:
    decision, provenance = make_decision()

    with pytest.raises(ValueError, match="approved_power_kw"):
        FeasibleDecision(decision, provenance, intent, power)


def test_boundary_and_fake_implementation_have_no_instance_state() -> None:
    evaluator = PassThroughFeasibility()

    assert FeasibilityBoundary.__slots__ == ()
    assert PassThroughFeasibility.__slots__ == ()
    assert not hasattr(evaluator, "__dict__")
    with pytest.raises(AttributeError):
        cast(Any, evaluator).cache = object()


def test_feasibility_module_has_no_algorithm_or_execution_dependency() -> None:
    module_path = Path(ems_strategy.__file__).parent / "feasibility.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "dataclasses",
        "decision_formation",
        "ems_strategy.decision",
        "ems_strategy.provenance",
        "math",
    }
    for forbidden in (
        "soc",
        "clip",
        "grid",
        "simulate(",
        "execute(",
        "Command",
    ):
        assert forbidden not in source


def test_public_api_exports_feasibility_contracts() -> None:
    from ems_strategy import __all__ as public_names

    assert "FeasibilityBoundary" in public_names
    assert "FeasibleDecision" in public_names
    assert ems_strategy.FeasibilityBoundary is FeasibilityBoundary
    assert ems_strategy.FeasibleDecision is FeasibleDecision
