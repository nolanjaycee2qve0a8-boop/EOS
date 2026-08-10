"""Tests for immutable EMS decision provenance."""

import ast
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

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
)
from kernel.decision import DecisionContext
from objective import (
    ObjectiveCapabilityActivationComposition,
    ObjectiveDescriptor,
)


def make_context() -> EMSContext:
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
    return EMSContext(source_context, composition, available)


def make_lineage() -> tuple[
    EMSContext,
    EMSStrategyDescriptor,
    EMSDecision,
]:
    context = make_context()
    strategy = EMSStrategyDescriptor("test-strategy", "1.0")
    decision = EMSDecision(
        context,
        strategy,
        DecisionIntent("charge"),
        2.0,
    )
    return context, strategy, decision


def test_provenance_preserves_exact_lineage_references() -> None:
    context, strategy, decision = make_lineage()

    provenance = DecisionProvenance(context, strategy, decision)

    assert provenance.source_context is context
    assert provenance.source_strategy is strategy
    assert provenance.decision is decision
    assert provenance.decision.source_context is provenance.source_context
    assert provenance.decision.source_strategy is provenance.source_strategy


def test_provenance_is_frozen_slotted_and_has_no_mutable_fields() -> None:
    context, strategy, decision = make_lineage()
    provenance = DecisionProvenance(context, strategy, decision)

    assert [field.name for field in fields(DecisionProvenance)] == [
        "source_context",
        "source_strategy",
        "decision",
    ]
    assert DecisionProvenance.__slots__ == (
        "source_context",
        "source_strategy",
        "decision",
    )
    assert not hasattr(provenance, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, provenance).decision = decision


def test_provenance_rejects_reconstructed_equal_context() -> None:
    context, strategy, decision = make_lineage()
    reconstructed = EMSContext(
        context.source_context,
        context.objective_composition,
        context.capability,
    )

    assert reconstructed == context
    assert reconstructed is not context
    with pytest.raises(ValueError, match="source_context identity"):
        DecisionProvenance(reconstructed, strategy, decision)


def test_provenance_rejects_reconstructed_equal_strategy_descriptor() -> None:
    context, strategy, decision = make_lineage()
    reconstructed = EMSStrategyDescriptor(strategy.name, strategy.version)

    assert reconstructed == strategy
    assert reconstructed is not strategy
    with pytest.raises(ValueError, match="source_strategy identity"):
        DecisionProvenance(context, reconstructed, decision)


@pytest.mark.parametrize(
    ("field_name", "values"),
    [
        ("source_context", (None, EMSStrategyDescriptor("test", "1"), None)),
        ("source_strategy", (make_context(), None, None)),
        ("decision", (make_context(), EMSStrategyDescriptor("test", "1"), None)),
    ],
)
def test_provenance_rejects_invalid_reference_types(
    field_name: str,
    values: tuple[object, object, object],
) -> None:
    with pytest.raises(TypeError, match=field_name):
        DecisionProvenance(*cast(Any, values))


def test_provenance_module_has_observation_only_dependencies() -> None:
    module_path = Path(ems_strategy.__file__).parent / "provenance.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "dataclasses",
        "ems_strategy.context",
        "ems_strategy.decision",
        "ems_strategy.descriptor",
    }
    for forbidden in (
        "copy(",
        "deepcopy(",
        "serialize(",
        "evaluate(",
        "simulate(",
        "execute(",
    ):
        assert forbidden not in source


def test_public_api_exports_decision_provenance() -> None:
    from ems_strategy import __all__ as public_names

    assert "DecisionProvenance" in public_names
    assert ems_strategy.DecisionProvenance is DecisionProvenance
