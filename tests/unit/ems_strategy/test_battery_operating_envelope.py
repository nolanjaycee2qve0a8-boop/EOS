"""Tests for the Battery operating-envelope feasibility boundary."""

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
    BatteryOperatingEnvelope,
    BatteryOperatingEnvelopeBoundary,
    BatteryOperatingEnvelopeFeasibility,
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


def make_decision(
    action: str,
    power_kw: float,
    *,
    soc: float,
) -> tuple[EMSDecision, DecisionProvenance]:
    source_context = DecisionContext(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        soc=soc,
        battery_power_limit_kw=10.0,
        battery_energy_capacity_kwh=20.0,
        pv_power_kw=5.0,
        load_power_kw=2.0,
        grid_power_kw=0.0,
        electricity_price_cny_per_kwh=0.5,
        reserve_soc=0.2,
        export_limit_kw=5.0,
    )
    required = CapabilityDescriptor("battery", "Required capability.")
    available = CapabilityDescriptor("battery", "Available capability.")
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
        ObjectiveDescriptor("battery", "Use Battery within its envelope."),
        active,
    )
    context = EMSContext(source_context, composition, available)
    strategy = EMSStrategyDescriptor("test-strategy", "1.0")
    decision = EMSDecision(
        context,
        strategy,
        DecisionIntent(cast(Any, action)),
        power_kw,
    )
    provenance = DecisionProvenance(context, strategy, decision)
    return decision, provenance


def make_envelope() -> BatteryOperatingEnvelope:
    return BatteryOperatingEnvelope(
        minimum_soc=0.2,
        maximum_soc=0.9,
        maximum_charge_power_kw=4.0,
        maximum_discharge_power_kw=3.0,
    )


class ExampleBatteryOperatingEnvelopeBoundary(BatteryOperatingEnvelopeBoundary):
    """Test-only implementation of the documented feasibility examples."""

    __slots__ = ()

    def _evaluate(
        self,
        decision: EMSDecision,
        *,
        provenance: DecisionProvenance,
        envelope: BatteryOperatingEnvelope,
    ) -> BatteryOperatingEnvelopeFeasibility:
        action = decision.intent.action
        soc = decision.source_context.source_context.soc
        if action == "charge":
            is_feasible = (
                soc < envelope.maximum_soc
                and decision.requested_power_kw <= envelope.maximum_charge_power_kw
            )
        elif action == "discharge":
            is_feasible = (
                soc > envelope.minimum_soc
                and decision.requested_power_kw <= envelope.maximum_discharge_power_kw
            )
        else:
            is_feasible = True
        return BatteryOperatingEnvelopeFeasibility(
            decision,
            provenance,
            envelope,
            is_feasible,
        )


def evaluate(
    action: str,
    power_kw: float,
    *,
    soc: float,
) -> BatteryOperatingEnvelopeFeasibility:
    decision, provenance = make_decision(action, power_kw, soc=soc)
    return ExampleBatteryOperatingEnvelopeBoundary().evaluate(
        decision,
        provenance=provenance,
        envelope=make_envelope(),
    )


def test_boundary_is_abstract_and_cannot_be_instantiated() -> None:
    assert issubclass(BatteryOperatingEnvelopeBoundary, ABC)
    assert inspect.isabstract(BatteryOperatingEnvelopeBoundary)
    assert getattr(
        BatteryOperatingEnvelopeBoundary._evaluate,
        "__isabstractmethod__",
        False,
    )
    with pytest.raises(TypeError):
        BatteryOperatingEnvelopeBoundary()  # type: ignore[abstract]


def test_charge_within_soc_and_power_limits_is_feasible() -> None:
    assert evaluate("charge", 4.0, soc=0.8).is_feasible is True


def test_discharge_within_soc_and_power_limits_is_feasible() -> None:
    assert evaluate("discharge", 3.0, soc=0.3).is_feasible is True


@pytest.mark.parametrize(
    ("action", "power_kw", "soc"),
    [("charge", 1.0, 0.9), ("discharge", 1.0, 0.2)],
)
def test_soc_boundary_is_infeasible(
    action: str,
    power_kw: float,
    soc: float,
) -> None:
    assert evaluate(action, power_kw, soc=soc).is_feasible is False


@pytest.mark.parametrize(
    ("action", "power_kw"),
    [("charge", 4.1), ("discharge", 3.1)],
)
def test_power_above_limit_is_infeasible(action: str, power_kw: float) -> None:
    assert evaluate(action, power_kw, soc=0.5).is_feasible is False


def test_result_preserves_exact_decision_provenance_and_envelope() -> None:
    decision, provenance = make_decision("charge", 2.0, soc=0.5)
    envelope = make_envelope()

    result = ExampleBatteryOperatingEnvelopeBoundary().evaluate(
        decision,
        provenance=provenance,
        envelope=envelope,
    )

    assert result.source_decision is decision
    assert result.source_provenance is provenance
    assert result.source_envelope is envelope


def test_result_is_frozen_slotted_and_contains_only_immutable_fields() -> None:
    decision, provenance = make_decision("idle", 0.0, soc=0.5)
    envelope = make_envelope()
    result = BatteryOperatingEnvelopeFeasibility(
        decision,
        provenance,
        envelope,
        True,
    )

    assert [field.name for field in fields(BatteryOperatingEnvelopeFeasibility)] == [
        "source_decision",
        "source_provenance",
        "source_envelope",
        "is_feasible",
    ]
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, result).is_feasible = False


def test_envelope_is_frozen_slotted_and_has_explicit_units() -> None:
    envelope = make_envelope()

    assert BatteryOperatingEnvelope.__slots__ == (
        "minimum_soc",
        "maximum_soc",
        "maximum_charge_power_kw",
        "maximum_discharge_power_kw",
    )
    assert not hasattr(envelope, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, envelope).maximum_charge_power_kw = 5.0
    assert "raw unitless fractions" in (BatteryOperatingEnvelope.__doc__ or "")
    assert "raw kW magnitudes" in (BatteryOperatingEnvelope.__doc__ or "")


def test_reconstructed_equal_decision_is_rejected() -> None:
    decision, provenance = make_decision("charge", 2.0, soc=0.5)
    reconstructed = EMSDecision(
        decision.source_context,
        decision.source_strategy,
        decision.intent,
        decision.requested_power_kw,
    )

    assert reconstructed == decision
    assert reconstructed is not decision
    with pytest.raises(ValueError, match="source_decision identity"):
        BatteryOperatingEnvelopeFeasibility(
            reconstructed,
            provenance,
            make_envelope(),
            True,
        )


def test_boundary_rejects_reconstructed_equal_envelope() -> None:
    decision, provenance = make_decision("charge", 2.0, soc=0.5)
    envelope = make_envelope()

    class ReconstructingBoundary(BatteryOperatingEnvelopeBoundary):
        __slots__ = ()

        def _evaluate(
            self,
            decision: EMSDecision,
            *,
            provenance: DecisionProvenance,
            envelope: BatteryOperatingEnvelope,
        ) -> BatteryOperatingEnvelopeFeasibility:
            reconstructed = BatteryOperatingEnvelope(
                envelope.minimum_soc,
                envelope.maximum_soc,
                envelope.maximum_charge_power_kw,
                envelope.maximum_discharge_power_kw,
            )
            return BatteryOperatingEnvelopeFeasibility(
                decision,
                provenance,
                reconstructed,
                True,
            )

    with pytest.raises(ValueError, match="source_envelope identity"):
        ReconstructingBoundary().evaluate(
            decision,
            provenance=provenance,
            envelope=envelope,
        )


def test_boundary_and_example_implementation_are_stateless() -> None:
    boundary = ExampleBatteryOperatingEnvelopeBoundary()

    assert BatteryOperatingEnvelopeBoundary.__slots__ == ()
    assert ExampleBatteryOperatingEnvelopeBoundary.__slots__ == ()
    assert not hasattr(boundary, "__dict__")
    with pytest.raises(AttributeError):
        cast(Any, boundary).cache = object()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"minimum_soc": -0.1},
        {"maximum_soc": 1.1},
        {"minimum_soc": 0.8, "maximum_soc": 0.7},
        {"maximum_charge_power_kw": -1.0},
        {"maximum_discharge_power_kw": float("inf")},
    ],
)
def test_envelope_rejects_invalid_limits(kwargs: dict[str, float]) -> None:
    values = {
        "minimum_soc": 0.2,
        "maximum_soc": 0.9,
        "maximum_charge_power_kw": 4.0,
        "maximum_discharge_power_kw": 3.0,
    }
    values.update(kwargs)

    with pytest.raises(ValueError):
        BatteryOperatingEnvelope(**values)


def test_module_has_no_execution_or_control_dependency() -> None:
    module_path = Path(ems_strategy.__file__).parent / "battery_operating_envelope.py"
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
        "math",
    }


def test_public_api_exports_battery_operating_envelope_contracts() -> None:
    assert "BatteryOperatingEnvelope" in ems_strategy.__all__
    assert "BatteryOperatingEnvelopeBoundary" in ems_strategy.__all__
    assert "BatteryOperatingEnvelopeFeasibility" in ems_strategy.__all__
    assert ems_strategy.BatteryOperatingEnvelope is BatteryOperatingEnvelope
    assert (
        ems_strategy.BatteryOperatingEnvelopeBoundary
        is BatteryOperatingEnvelopeBoundary
    )
    assert (
        ems_strategy.BatteryOperatingEnvelopeFeasibility
        is BatteryOperatingEnvelopeFeasibility
    )
