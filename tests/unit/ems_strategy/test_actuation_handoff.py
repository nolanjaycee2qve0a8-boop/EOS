"""Tests for the explicit EMS-to-Simulator actuation handoff contract."""

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
    ActuationHandoffBoundary,
    ActuationHandoffResult,
    DecisionProvenance,
    EMSContext,
    EMSDecision,
    EMSStrategyDescriptor,
    FeasibleDecision,
)
from kernel.decision import (
    DecisionContext,
    FeasibleDecisionIntent,
)
from kernel.decision import (
    DecisionIntent as SimulatorDecisionIntent,
)
from objective import (
    ObjectiveCapabilityActivationComposition,
    ObjectiveDescriptor,
)
from simulator import BatterySimulationActuation


def make_feasible_decision(
    action: str = "charge",
    power_kw: float = 2.0,
) -> FeasibleDecision:
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
    intent = DecisionIntent(cast(Any, action))
    decision = EMSDecision(context, strategy, intent, power_kw)
    provenance = DecisionProvenance(context, strategy, decision)
    return FeasibleDecision(decision, provenance, intent, power_kw)


def make_actuation(feasible_decision: FeasibleDecision) -> BatterySimulationActuation:
    action = feasible_decision.approved_intent.action
    magnitude = feasible_decision.approved_power_kw
    signed_power_kw = (
        magnitude
        if action == "charge"
        else -magnitude
        if action == "discharge"
        else 0.0
    )
    simulator_intent = SimulatorDecisionIntent(signed_power_kw)
    simulator_feasible = FeasibleDecisionIntent(simulator_intent)
    return BatterySimulationActuation(simulator_feasible, signed_power_kw)


class FakeActuationHandoff(ActuationHandoffBoundary):
    """Test-only mapper implementing the frozen sign convention."""

    __slots__ = ()

    def _handoff(
        self,
        feasible_decision: FeasibleDecision,
    ) -> ActuationHandoffResult:
        actuation = make_actuation(feasible_decision)
        return ActuationHandoffResult(feasible_decision, actuation)


class ReconstructingActuationHandoff(ActuationHandoffBoundary):
    """Test-only invalid implementation that reconstructs the source artifact."""

    __slots__ = ()

    def _handoff(
        self,
        feasible_decision: FeasibleDecision,
    ) -> ActuationHandoffResult:
        reconstructed = FeasibleDecision(
            feasible_decision.source_decision,
            feasible_decision.source_provenance,
            feasible_decision.approved_intent,
            feasible_decision.approved_power_kw,
        )
        return ActuationHandoffResult(reconstructed, make_actuation(reconstructed))


def test_boundary_is_abstract_and_cannot_be_instantiated() -> None:
    assert issubclass(ActuationHandoffBoundary, ABC)
    assert inspect.isabstract(ActuationHandoffBoundary)
    assert getattr(ActuationHandoffBoundary._handoff, "__isabstractmethod__", False)
    with pytest.raises(TypeError):
        ActuationHandoffBoundary()  # type: ignore[abstract]


@pytest.mark.parametrize(
    ("action", "magnitude", "signed_power"),
    [
        ("charge", 2.0, 2.0),
        ("discharge", 1.5, -1.5),
        ("idle", 0.0, 0.0),
    ],
)
def test_fake_handoff_preserves_exact_references_and_sign_mapping(
    action: str,
    magnitude: float,
    signed_power: float,
) -> None:
    feasible = make_feasible_decision(action, magnitude)

    result = FakeActuationHandoff().handoff(feasible)

    assert isinstance(result, ActuationHandoffResult)
    assert result.source_feasible_decision is feasible
    assert isinstance(result.actuation, BatterySimulationActuation)
    assert result.actuation.battery_power_kw == signed_power


def test_result_preserves_exact_actuation_identity() -> None:
    feasible = make_feasible_decision()
    actuation = make_actuation(feasible)

    result = ActuationHandoffResult(feasible, actuation)

    assert result.source_feasible_decision is feasible
    assert result.actuation is actuation


def test_boundary_rejects_reconstructed_equal_feasible_decision() -> None:
    feasible = make_feasible_decision()

    with pytest.raises(ValueError, match="exact source_feasible_decision identity"):
        ReconstructingActuationHandoff().handoff(feasible)


def test_result_rejects_inconsistent_signed_power() -> None:
    feasible = make_feasible_decision("charge", 2.0)
    simulator_intent = SimulatorDecisionIntent(-2.0)
    simulator_feasible = FeasibleDecisionIntent(simulator_intent)
    wrong_actuation = BatterySimulationActuation(simulator_feasible, -2.0)

    with pytest.raises(ValueError, match="must match"):
        ActuationHandoffResult(feasible, wrong_actuation)


def test_result_is_frozen_slotted_and_has_no_mutable_fields() -> None:
    feasible = make_feasible_decision()
    result = ActuationHandoffResult(feasible, make_actuation(feasible))

    assert [field.name for field in fields(ActuationHandoffResult)] == [
        "source_feasible_decision",
        "actuation",
    ]
    assert ActuationHandoffResult.__slots__ == (
        "source_feasible_decision",
        "actuation",
    )
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, result).actuation = result.actuation


def test_boundary_and_fake_have_no_instance_state() -> None:
    handoff = FakeActuationHandoff()

    assert ActuationHandoffBoundary.__slots__ == ()
    assert FakeActuationHandoff.__slots__ == ()
    assert not hasattr(handoff, "__dict__")
    with pytest.raises(AttributeError):
        cast(Any, handoff).cache = object()


def test_boundary_rejects_invalid_input_and_output_types() -> None:
    class InvalidOutputHandoff(ActuationHandoffBoundary):
        __slots__ = ()

        def _handoff(
            self,
            feasible_decision: FeasibleDecision,
        ) -> ActuationHandoffResult:
            return cast(ActuationHandoffResult, object())

    with pytest.raises(TypeError, match="feasible_decision"):
        FakeActuationHandoff().handoff(cast(Any, object()))
    with pytest.raises(TypeError, match="must return"):
        InvalidOutputHandoff().handoff(make_feasible_decision())


def test_handoff_module_is_only_an_explicit_adapter_dependency() -> None:
    module_path = Path(ems_strategy.__file__).parent / "handoff.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "dataclasses",
        "ems_strategy.feasibility",
        "simulator",
    }


def test_public_api_exports_handoff_contracts() -> None:
    from ems_strategy import __all__ as public_names

    assert "ActuationHandoffBoundary" in public_names
    assert "ActuationHandoffResult" in public_names
    assert ems_strategy.ActuationHandoffBoundary is ActuationHandoffBoundary
    assert ems_strategy.ActuationHandoffResult is ActuationHandoffResult
