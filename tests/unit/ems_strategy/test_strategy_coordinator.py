"""Tests for caller-configured, stateless EMS strategy coordination."""

import ast
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, cast

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
    EMSStrategyBoundary,
    EMSStrategyDescriptor,
    StrategyCoordinator,
    StrategyCoordinatorConfiguration,
)
from kernel.decision import DecisionContext
from objective import ObjectiveCapabilityActivationComposition, ObjectiveDescriptor

evaluation_order: list[EMSStrategyDescriptor] = []


class LowPriorityStrategy(EMSStrategyBoundary):
    """Test-only strategy that makes an idle request."""

    __slots__ = ()

    descriptor: ClassVar[EMSStrategyDescriptor] = EMSStrategyDescriptor("low", "1.0")
    contexts: ClassVar[list[EMSContext]] = []
    decisions: ClassVar[list[EMSDecision]] = []

    def evaluate(self, context: EMSContext) -> EMSDecision:
        evaluation_order.append(self.descriptor)
        self.contexts.append(context)
        decision = EMSDecision(
            context,
            self.descriptor,
            DecisionIntent("idle"),
            0.0,
        )
        self.decisions.append(decision)
        return decision


class HighPriorityStrategy(EMSStrategyBoundary):
    """Test-only strategy that makes a charge request."""

    __slots__ = ()

    descriptor: ClassVar[EMSStrategyDescriptor] = EMSStrategyDescriptor("high", "1.0")
    contexts: ClassVar[list[EMSContext]] = []
    decisions: ClassVar[list[EMSDecision]] = []

    def evaluate(self, context: EMSContext) -> EMSDecision:
        evaluation_order.append(self.descriptor)
        self.contexts.append(context)
        decision = EMSDecision(
            context,
            self.descriptor,
            DecisionIntent("charge"),
            2.0,
        )
        self.decisions.append(decision)
        return decision


def make_context() -> EMSContext:
    source_context = DecisionContext(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        soc=0.5,
        battery_power_limit_kw=3.0,
        battery_energy_capacity_kwh=10.0,
        pv_power_kw=2.0,
        load_power_kw=2.0,
        grid_power_kw=0.0,
        electricity_price_cny_per_kwh=0.5,
        reserve_soc=0.2,
        export_limit_kw=5.0,
    )
    required = CapabilityDescriptor("test", "Required capability.")
    available = CapabilityDescriptor("test", "Available capability.")
    matches = CapabilityMatchCollection(
        RequiredCapabilityCollection((required,)),
        AvailableCapabilityCollection((available,)),
        (CapabilityMatch(required, available),),
        (),
    )
    composition = ObjectiveCapabilityActivationComposition(
        ObjectiveDescriptor("test", "Test objective."),
        ActiveCapabilityCollection(matches, (available,), ()),
    )
    return EMSContext(source_context, composition, available)


@pytest.fixture(autouse=True)
def clear_test_strategy_evidence() -> None:
    evaluation_order.clear()
    LowPriorityStrategy.contexts.clear()
    LowPriorityStrategy.decisions.clear()
    HighPriorityStrategy.contexts.clear()
    HighPriorityStrategy.decisions.clear()


def make_coordinator() -> tuple[StrategyCoordinator, tuple[EMSStrategyBoundary, ...]]:
    strategies: tuple[EMSStrategyBoundary, ...] = (
        LowPriorityStrategy(),
        HighPriorityStrategy(),
    )
    coordinator = StrategyCoordinator(
        StrategyCoordinatorConfiguration(
            (HighPriorityStrategy.descriptor, LowPriorityStrategy.descriptor)
        ),
        strategies,
    )
    return coordinator, strategies


def test_coordinator_evaluates_all_strategies_once_in_caller_order() -> None:
    coordinator, strategies = make_coordinator()
    context = make_context()

    coordinator.evaluate(context)

    assert coordinator.strategies is strategies
    assert evaluation_order == [
        LowPriorityStrategy.descriptor,
        HighPriorityStrategy.descriptor,
    ]
    assert len(LowPriorityStrategy.contexts) == 1
    assert LowPriorityStrategy.contexts[0] is context
    assert len(HighPriorityStrategy.contexts) == 1
    assert HighPriorityStrategy.contexts[0] is context


def test_priority_selects_exact_high_priority_strategy_decision() -> None:
    coordinator, _ = make_coordinator()
    context = make_context()

    decision = coordinator.evaluate(context)

    assert decision is HighPriorityStrategy.decisions[0]
    assert decision is not LowPriorityStrategy.decisions[0]
    assert decision.source_strategy is HighPriorityStrategy.descriptor


def test_selected_decision_preserves_exact_context_and_provenance() -> None:
    coordinator, _ = make_coordinator()
    context = make_context()

    decision = coordinator.evaluate(context)
    provenance = DecisionProvenance(context, HighPriorityStrategy.descriptor, decision)

    assert decision.source_context is context
    assert decision.source_strategy is HighPriorityStrategy.descriptor
    assert provenance.decision is decision
    assert provenance.source_context is context
    assert provenance.source_strategy is HighPriorityStrategy.descriptor


def test_configuration_and_coordinator_are_frozen_slotted_and_tuple_preserving() -> (
    None
):
    coordinator, strategies = make_coordinator()
    priority = coordinator.configuration.strategy_priority

    assert [field.name for field in fields(StrategyCoordinatorConfiguration)] == [
        "strategy_priority"
    ]
    assert [field.name for field in fields(StrategyCoordinator)] == [
        "configuration",
        "strategies",
    ]
    assert coordinator.configuration.strategy_priority is priority
    assert coordinator.strategies is strategies
    assert not hasattr(coordinator.configuration, "__dict__")
    assert not hasattr(coordinator, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, coordinator).strategies = ()
    with pytest.raises((AttributeError, TypeError)):
        cast(Any, coordinator).cache = object()


def test_reconstructed_equal_priority_descriptor_is_rejected() -> None:
    reconstructed = EMSStrategyDescriptor("high", "1.0")
    assert reconstructed == HighPriorityStrategy.descriptor
    assert reconstructed is not HighPriorityStrategy.descriptor

    with pytest.raises(ValueError, match="exact identity"):
        StrategyCoordinator(
            StrategyCoordinatorConfiguration(
                (reconstructed, LowPriorityStrategy.descriptor)
            ),
            (LowPriorityStrategy(), HighPriorityStrategy()),
        )


def test_duplicate_descriptor_identity_and_invalid_input_types_are_rejected() -> None:
    with pytest.raises(ValueError, match="repeat"):
        StrategyCoordinatorConfiguration(
            (LowPriorityStrategy.descriptor, LowPriorityStrategy.descriptor)
        )
    with pytest.raises(TypeError, match="tuple"):
        StrategyCoordinatorConfiguration(cast(Any, [LowPriorityStrategy.descriptor]))
    with pytest.raises(TypeError, match="configuration"):
        StrategyCoordinator(cast(Any, object()), ())
    with pytest.raises(TypeError, match="context"):
        make_coordinator()[0].evaluate(cast(Any, object()))


def test_coordinator_module_has_no_runtime_or_device_dependency() -> None:
    module_path = Path(ems_strategy.__file__).parent / "coordinator.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "dataclasses",
        "ems_strategy.boundary",
        "ems_strategy.context",
        "ems_strategy.decision",
        "ems_strategy.descriptor",
    }
    for forbidden_name in (
        "cache",
        "history",
        "Simulator",
        "Command",
        "BatterySimulationActuation",
    ):
        assert forbidden_name not in source


def test_public_api_exports_coordinator_contracts() -> None:
    assert "StrategyCoordinator" in ems_strategy.__all__
    assert "StrategyCoordinatorConfiguration" in ems_strategy.__all__
    assert ems_strategy.StrategyCoordinator is StrategyCoordinator
    assert (
        ems_strategy.StrategyCoordinatorConfiguration
        is StrategyCoordinatorConfiguration
    )
