"""Tests for the Zero Export feasibility contract boundary."""

import ast
import inspect
from abc import ABC
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
    ZeroExportBoundary,
    ZeroExportFeasibility,
)
from kernel.decision import DecisionContext
from objective import (
    ObjectiveCapabilityActivationComposition,
    ObjectiveDescriptor,
)


def make_decision() -> tuple[EMSDecision, DecisionProvenance]:
    source_context = DecisionContext(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        soc=0.5,
        battery_power_limit_kw=3.0,
        battery_energy_capacity_kwh=10.0,
        pv_power_kw=5.0,
        load_power_kw=2.0,
        grid_power_kw=-3.0,
        electricity_price_cny_per_kwh=0.5,
        reserve_soc=0.2,
        export_limit_kw=0.0,
    )
    required = CapabilityDescriptor("zero-export", "Required capability.")
    available = CapabilityDescriptor("zero-export", "Available capability.")
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
        ObjectiveDescriptor("zero-export", "Avoid Grid export."),
        active,
    )
    context = EMSContext(source_context, composition, available)
    strategy = EMSStrategyDescriptor("test-strategy", "1.0")
    decision = EMSDecision(context, strategy, DecisionIntent("charge"), 3.0)
    provenance = DecisionProvenance(context, strategy, decision)
    return decision, provenance


class PreservingZeroExportBoundary(ZeroExportBoundary):
    """Test-only boundary representing a feasible source request."""

    __slots__ = ()

    def _evaluate(
        self,
        decision: EMSDecision,
        *,
        provenance: DecisionProvenance,
    ) -> ZeroExportFeasibility:
        return ZeroExportFeasibility(decision, provenance, True)


class RiskZeroExportBoundary(ZeroExportBoundary):
    """Test-only boundary representing risk without correction logic."""

    __slots__ = ()

    def _evaluate(
        self,
        decision: EMSDecision,
        *,
        provenance: DecisionProvenance,
    ) -> ZeroExportFeasibility:
        return ZeroExportFeasibility(decision, provenance, False)


def test_boundary_is_abstract_and_cannot_be_instantiated() -> None:
    assert issubclass(ZeroExportBoundary, ABC)
    assert inspect.isabstract(ZeroExportBoundary)
    assert getattr(ZeroExportBoundary._evaluate, "__isabstractmethod__", False)
    with pytest.raises(TypeError):
        ZeroExportBoundary()  # type: ignore[abstract]


def test_pv_surplus_charge_request_is_preserved_as_feasible() -> None:
    decision, provenance = make_decision()

    result = PreservingZeroExportBoundary().evaluate(
        decision,
        provenance=provenance,
    )

    assert result.is_feasible is True
    assert result.source_decision is decision
    assert result.source_provenance is provenance
    assert result.source_decision.intent.action == "charge"


def test_future_export_risk_is_represented_without_correction() -> None:
    decision, provenance = make_decision()

    result = RiskZeroExportBoundary().evaluate(
        decision,
        provenance=provenance,
    )

    assert result.is_feasible is False
    assert result.source_decision is decision
    assert result.source_provenance is provenance


def test_result_is_frozen_slotted_and_has_no_mutable_fields() -> None:
    decision, provenance = make_decision()
    result = ZeroExportFeasibility(decision, provenance, True)

    assert [field.name for field in fields(ZeroExportFeasibility)] == [
        "source_decision",
        "source_provenance",
        "is_feasible",
    ]
    assert ZeroExportFeasibility.__slots__ == (
        "source_decision",
        "source_provenance",
        "is_feasible",
    )
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, result).is_feasible = False


def test_result_rejects_reconstructed_equal_decision() -> None:
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
        ZeroExportFeasibility(reconstructed, provenance, True)


def test_boundary_rejects_reconstructed_equal_provenance() -> None:
    decision, provenance = make_decision()

    class ReconstructingBoundary(ZeroExportBoundary):
        __slots__ = ()

        def _evaluate(
            self,
            decision: EMSDecision,
            *,
            provenance: DecisionProvenance,
        ) -> ZeroExportFeasibility:
            reconstructed = DecisionProvenance(
                provenance.source_context,
                provenance.source_strategy,
                provenance.decision,
            )
            return ZeroExportFeasibility(decision, reconstructed, True)

    with pytest.raises(ValueError, match="source_provenance identity"):
        ReconstructingBoundary().evaluate(decision, provenance=provenance)


def test_boundary_and_implementations_are_stateless() -> None:
    boundary = PreservingZeroExportBoundary()

    assert ZeroExportBoundary.__slots__ == ()
    assert PreservingZeroExportBoundary.__slots__ == ()
    assert not hasattr(boundary, "__dict__")
    with pytest.raises(AttributeError):
        cast(Any, boundary).cache = object()


def test_invalid_reference_and_status_types_are_rejected() -> None:
    decision, provenance = make_decision()

    with pytest.raises(TypeError, match="source_decision"):
        ZeroExportFeasibility(cast(Any, object()), provenance, True)
    with pytest.raises(TypeError, match="source_provenance"):
        ZeroExportFeasibility(decision, cast(Any, object()), True)
    with pytest.raises(TypeError, match="is_feasible"):
        ZeroExportFeasibility(decision, provenance, cast(Any, 1))
    with pytest.raises(TypeError, match="decision"):
        PreservingZeroExportBoundary().evaluate(
            cast(Any, object()),
            provenance=provenance,
        )


def test_zero_export_module_has_no_simulator_or_control_dependency() -> None:
    module_path = Path(ems_strategy.__file__).parent / "zero_export.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "dataclasses",
        "ems_strategy.decision",
        "ems_strategy.provenance",
    }


def test_public_api_exports_zero_export_contracts() -> None:
    assert "ZeroExportBoundary" in ems_strategy.__all__
    assert "ZeroExportFeasibility" in ems_strategy.__all__
    assert ems_strategy.ZeroExportBoundary is ZeroExportBoundary
    assert ems_strategy.ZeroExportFeasibility is ZeroExportFeasibility
