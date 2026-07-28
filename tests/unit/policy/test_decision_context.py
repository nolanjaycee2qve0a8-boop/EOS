"""Tests for the DecisionContextPolicy contract boundary."""

from abc import ABC
from datetime import UTC, datetime
from inspect import isabstract, signature
from typing import Any, cast, get_type_hints

import pytest

from kernel.context import EnergySystemContext
from kernel.decision import DecisionContext, DecisionResult
from kernel.policy import DecisionContextPolicy, EMSPolicy

FIXED_RESULT = DecisionResult.empty()


class EmptyDecisionContextPolicy(DecisionContextPolicy):
    """Minimal test-only implementation of the abstract contract."""

    __slots__ = ()

    def evaluate(self, context: DecisionContext) -> DecisionResult:
        return FIXED_RESULT


class RecordingDecisionContextPolicy(DecisionContextPolicy):
    """Test-only implementation that observes the supplied identity."""

    __slots__ = ("received_context",)

    def __init__(self) -> None:
        self.received_context: DecisionContext | None = None

    def evaluate(self, context: DecisionContext) -> DecisionResult:
        self.received_context = context
        return FIXED_RESULT


def make_context() -> DecisionContext:
    return DecisionContext(
        timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        soc=0.5,
        battery_power_limit_kw=50.0,
        battery_energy_capacity_kwh=100.0,
        pv_power_kw=40.0,
        load_power_kw=30.0,
        grid_power_kw=-10.0,
        electricity_price_cny_per_kwh=0.25,
        reserve_soc=0.2,
        export_limit_kw=15.0,
    )


def test_decision_context_policy_is_abstract_interface() -> None:
    assert issubclass(DecisionContextPolicy, ABC)
    assert isabstract(DecisionContextPolicy)
    assert getattr(
        DecisionContextPolicy.evaluate,
        "__isabstractmethod__",
        False,
    )


def test_cannot_instantiate_decision_context_policy() -> None:
    with pytest.raises(TypeError):
        DecisionContextPolicy()  # type: ignore[abstract]


def test_evaluate_signature_accepts_only_decision_context() -> None:
    parameters = list(signature(DecisionContextPolicy.evaluate).parameters)
    hints = get_type_hints(DecisionContextPolicy.evaluate)

    assert parameters == ["self", "context"]
    assert hints == {
        "context": DecisionContext,
        "return": DecisionResult,
    }


def test_return_contract_is_documented() -> None:
    documentation = DecisionContextPolicy.evaluate.__doc__

    assert documentation is not None
    assert "DecisionResult" in documentation
    assert "DecisionContext" in documentation


def test_minimal_policy_returns_exact_decision_result() -> None:
    result = EmptyDecisionContextPolicy().evaluate(make_context())

    assert result is FIXED_RESULT


def test_policy_receives_exact_context_identity() -> None:
    context = make_context()
    policy = RecordingDecisionContextPolicy()

    policy.evaluate(context)

    assert policy.received_context is context


def test_evaluation_does_not_mutate_context() -> None:
    context = make_context()
    expected = make_context()
    timestamp = context.timestamp

    EmptyDecisionContextPolicy().evaluate(context)

    assert context == expected
    assert context.timestamp is timestamp


def test_abstract_boundary_has_no_instance_state() -> None:
    policy = EmptyDecisionContextPolicy()

    assert DecisionContextPolicy.__slots__ == ()
    assert not hasattr(policy, "__dict__")
    with pytest.raises(AttributeError):
        cast(Any, policy).cache = {}


def test_new_policy_is_independent_from_legacy_ems_policy() -> None:
    assert cast(object, DecisionContextPolicy) is not EMSPolicy
    assert not issubclass(DecisionContextPolicy, EMSPolicy)
    assert not issubclass(EMSPolicy, DecisionContextPolicy)


def test_legacy_ems_policy_contract_remains_unchanged() -> None:
    hints = get_type_hints(EMSPolicy.evaluate)

    assert hints == {
        "context": EnergySystemContext,
        "return": DecisionResult,
    }
