"""Tests for the DecisionContext policy implementation boundary."""

import ast
import inspect
from abc import ABC
from datetime import UTC, datetime
from typing import Any, cast, get_type_hints

import pytest

from kernel.context import EnergySystemContext
from kernel.decision import (
    DecisionContext,
    DecisionContextResult,
    DecisionIntent,
    DecisionResult,
)
from kernel.policy import (
    DecisionContextPolicy,
    DecisionContextPolicyImplementation,
    EMSPolicy,
)
from kernel.policy import implementation as implementation_module

FIXED_INTENT = DecisionIntent(5.0)
FIXED_RESULT = DecisionContextResult(FIXED_INTENT)


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


class MinimalPolicyImplementation(DecisionContextPolicyImplementation):
    """Test-only implementation that returns one existing result."""

    __slots__ = ()

    def evaluate(self, context: DecisionContext) -> DecisionContextResult:
        return FIXED_RESULT


def test_implementation_boundary_is_abstract_extension_only() -> None:
    assert issubclass(DecisionContextPolicyImplementation, ABC)
    assert issubclass(
        DecisionContextPolicyImplementation,
        DecisionContextPolicy,
    )
    assert inspect.isabstract(DecisionContextPolicyImplementation)
    with pytest.raises(TypeError):
        DecisionContextPolicyImplementation()  # type: ignore[abstract]


def test_concrete_implementation_uses_inherited_evaluate_contract() -> None:
    parameters = list(
        inspect.signature(DecisionContextPolicyImplementation.evaluate).parameters
    )
    hints = get_type_hints(DecisionContextPolicyImplementation.evaluate)

    assert parameters == ["self", "context"]
    assert hints == {
        "context": DecisionContext,
        "return": DecisionContextResult,
    }


def test_concrete_implementation_preserves_result_and_intent_identity() -> None:
    result = MinimalPolicyImplementation().evaluate(make_context())

    assert result is FIXED_RESULT
    assert result.intent is FIXED_INTENT


def test_concrete_implementation_receives_exact_context_identity() -> None:
    received: list[DecisionContext] = []

    class RecordingImplementation(DecisionContextPolicyImplementation):
        __slots__ = ()

        def evaluate(
            self,
            context: DecisionContext,
        ) -> DecisionContextResult:
            received.append(context)
            return FIXED_RESULT

    context = make_context()
    RecordingImplementation().evaluate(context)

    assert received == [context]
    assert received[0] is context


def test_implementation_boundary_has_no_instance_state() -> None:
    implementation = MinimalPolicyImplementation()

    assert DecisionContextPolicyImplementation.__slots__ == ()
    assert not hasattr(implementation, "__dict__")
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
        assert not hasattr(implementation, forbidden)
    with pytest.raises(AttributeError):
        cast(Any, implementation).cache = {}


def test_implementation_module_has_no_forbidden_dependencies() -> None:
    source = inspect.getsource(implementation_module)
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {"kernel.policy.decision_context"}
    for forbidden in (
        "runtime",
        "dispatch",
        "device",
        "persistence",
        "telemetry",
        "optimization",
        "forecast",
    ):
        assert all(
            forbidden not in module for module in imported_modules if module is not None
        )


def test_legacy_ems_policy_contract_remains_independent() -> None:
    assert not issubclass(DecisionContextPolicyImplementation, EMSPolicy)
    assert not issubclass(EMSPolicy, DecisionContextPolicyImplementation)
    assert get_type_hints(EMSPolicy.evaluate) == {
        "context": EnergySystemContext,
        "return": DecisionResult,
    }


def test_public_import_works() -> None:
    assert DecisionContextPolicyImplementation.__name__ == (
        "DecisionContextPolicyImplementation"
    )
