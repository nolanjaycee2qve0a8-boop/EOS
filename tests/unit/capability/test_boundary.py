"""Tests for the EMS capability extension boundary."""

import ast
import inspect
from abc import ABC
from datetime import UTC, datetime
from typing import Any, cast, get_type_hints

import pytest

from capability import EMSCapabilityBoundary
from capability import base as capability_base_module
from kernel.decision import DecisionContext, DecisionIntent
from kernel.policy import DecisionContextPolicy

FIXED_INTENT = DecisionIntent(2.0)


def make_context() -> DecisionContext:
    return DecisionContext(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        soc=0.5,
        battery_power_limit_kw=50.0,
        battery_energy_capacity_kwh=100.0,
        pv_power_kw=25.0,
        load_power_kw=20.0,
        grid_power_kw=-5.0,
        electricity_price_cny_per_kwh=0.5,
        reserve_soc=0.2,
        export_limit_kw=10.0,
    )


class MinimalCapability(EMSCapabilityBoundary):
    """Test-only capability with no production business behavior."""

    __slots__ = ()

    def evaluate(self, context: DecisionContext) -> DecisionIntent:
        return FIXED_INTENT


def test_capability_boundary_is_abstract() -> None:
    assert issubclass(EMSCapabilityBoundary, ABC)
    assert inspect.isabstract(EMSCapabilityBoundary)
    with pytest.raises(TypeError):
        EMSCapabilityBoundary()  # type: ignore[abstract]


def test_evaluate_contract_accepts_context_and_returns_intent() -> None:
    parameters = list(inspect.signature(EMSCapabilityBoundary.evaluate).parameters)
    hints = get_type_hints(EMSCapabilityBoundary.evaluate)

    assert parameters == ["self", "context"]
    assert hints == {
        "context": DecisionContext,
        "return": DecisionIntent,
    }


def test_concrete_capability_receives_exact_context_identity() -> None:
    received: list[DecisionContext] = []

    class RecordingCapability(EMSCapabilityBoundary):
        __slots__ = ()

        def evaluate(self, context: DecisionContext) -> DecisionIntent:
            received.append(context)
            return FIXED_INTENT

    context = make_context()
    intent = RecordingCapability().evaluate(context)

    assert received[0] is context
    assert intent is FIXED_INTENT


def test_boundary_has_no_instance_state() -> None:
    capability = MinimalCapability()

    assert EMSCapabilityBoundary.__slots__ == ()
    assert not hasattr(capability, "__dict__")
    for forbidden in (
        "runtime",
        "dispatcher",
        "device",
        "storage",
        "cache",
        "history",
        "commands",
        "events",
    ):
        assert not hasattr(capability, forbidden)
    with pytest.raises(AttributeError):
        cast(Any, capability).cache = {}


def test_boundary_is_independent_from_policy_contract() -> None:
    assert not issubclass(EMSCapabilityBoundary, DecisionContextPolicy)
    assert not issubclass(DecisionContextPolicy, EMSCapabilityBoundary)


def test_boundary_module_has_only_stable_contract_dependencies() -> None:
    source = inspect.getsource(capability_base_module)
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {"abc", "kernel.decision"}
    for forbidden in (
        "runtime",
        "dispatch",
        "device",
        "persistence",
        "telemetry",
        "optimization",
        "forecast",
        "constraint",
    ):
        assert all(
            forbidden not in module for module in imported_modules if module is not None
        )


def test_public_import_includes_capability_boundary() -> None:
    from capability import __all__ as public_names

    assert "EMSCapabilityBoundary" in public_names
    assert EMSCapabilityBoundary.__name__ == "EMSCapabilityBoundary"
