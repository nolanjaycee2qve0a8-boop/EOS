"""Tests for the abstract stateless EMS Strategy boundary."""

import ast
import inspect
from abc import ABC
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
    EMSContext,
    EMSDecision,
    EMSStrategyBoundary,
    EMSStrategyDescriptor,
)
from kernel.decision import DecisionContext
from objective import (
    ObjectiveCapabilityActivationComposition,
    ObjectiveDescriptor,
)


class MinimalStrategy(EMSStrategyBoundary):
    """Test-only conforming strategy with no retained state or business logic."""

    __slots__ = ()

    def evaluate(self, context: EMSContext) -> EMSDecision:
        if not isinstance(context, EMSContext):
            raise TypeError("context must be an EMSContext")
        return EMSDecision(
            source_context=context,
            source_strategy=EMSStrategyDescriptor("test-only", "1.0"),
            intent=DecisionIntent("idle"),
            requested_power_kw=0.0,
        )


def make_context() -> EMSContext:
    source_context = DecisionContext(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        soc=0.5,
        battery_power_limit_kw=3.0,
        battery_energy_capacity_kwh=10.0,
        pv_power_kw=1.0,
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


def test_boundary_is_abstract_and_cannot_be_instantiated() -> None:
    assert issubclass(EMSStrategyBoundary, ABC)
    assert inspect.isabstract(EMSStrategyBoundary)
    assert getattr(EMSStrategyBoundary.evaluate, "__isabstractmethod__", False)
    with pytest.raises(TypeError):
        EMSStrategyBoundary()  # type: ignore[abstract]


def test_boundary_signature_is_exact() -> None:
    signature = inspect.signature(EMSStrategyBoundary.evaluate)
    hints = get_type_hints(EMSStrategyBoundary.evaluate)

    assert list(signature.parameters) == ["self", "context"]
    assert hints == {"context": EMSContext, "return": EMSDecision}


def test_minimal_concrete_strategy_can_be_instantiated() -> None:
    strategy = MinimalStrategy()

    assert isinstance(strategy, EMSStrategyBoundary)
    assert not inspect.isabstract(MinimalStrategy)


def test_evaluate_receives_context_and_returns_decision_with_exact_identity() -> None:
    strategy = MinimalStrategy()
    context = make_context()

    decision = strategy.evaluate(context)

    assert isinstance(decision, EMSDecision)
    assert decision.source_context is context


def test_minimal_strategy_rejects_invalid_context_type() -> None:
    with pytest.raises(TypeError, match="EMSContext"):
        MinimalStrategy().evaluate(cast(Any, None))


def test_boundary_and_minimal_strategy_are_stateless_and_empty_slotted() -> None:
    strategy = MinimalStrategy()

    assert EMSStrategyBoundary.__slots__ == ()
    assert MinimalStrategy.__slots__ == ()
    assert not hasattr(strategy, "__dict__")
    assert not hasattr(strategy, "__weakref__")
    with pytest.raises(AttributeError):
        cast(Any, strategy).cache = object()


def test_boundary_defines_no_execution_or_state_ownership() -> None:
    for forbidden_name in (
        "cache",
        "history",
        "runtime",
        "simulator",
        "device",
        "command",
        "constraint",
        "dispatch",
        "schedule",
    ):
        assert not hasattr(EMSStrategyBoundary, forbidden_name)


def test_boundary_module_has_only_contract_dependencies() -> None:
    module_path = Path(ems_strategy.__file__).parent / "boundary.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "ems_strategy.context",
        "ems_strategy.decision",
    }
    for forbidden_call in ("copy(", "deepcopy(", "serialize(", "simulate("):
        assert forbidden_call not in source


def test_public_api_exports_boundary() -> None:
    from ems_strategy import __all__ as public_names

    assert "EMSStrategyBoundary" in public_names
    assert ems_strategy.EMSStrategyBoundary is EMSStrategyBoundary
