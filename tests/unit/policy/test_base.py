"""Tests for the abstract EMS policy contract."""

from abc import ABC
from inspect import isabstract, signature
from typing import get_type_hints

import pytest

from kernel.context import EnergySystemContext
from kernel.decision import DecisionResult
from kernel.policy import EMSPolicy
from kernel.power import PowerFlow


class EmptyEMSPolicy(EMSPolicy):
    """Minimal contract implementation used only to test the interface."""

    __slots__ = ()

    def evaluate(self, context: EnergySystemContext) -> DecisionResult:
        return DecisionResult.empty()


def make_context() -> EnergySystemContext:
    return EnergySystemContext(
        assets=(),
        states=(),
        power_flow=PowerFlow(
            pv_power_kw=0.0,
            load_power_kw=0.0,
            battery_power_kw=0.0,
            grid_power_kw=0.0,
        ),
    )


def test_ems_policy_is_abstract_interface() -> None:
    assert issubclass(EMSPolicy, ABC)
    assert isabstract(EMSPolicy)
    assert getattr(EMSPolicy.evaluate, "__isabstractmethod__", False)


def test_cannot_instantiate_base_policy() -> None:
    with pytest.raises(TypeError):
        EMSPolicy()  # type: ignore[abstract]


def test_evaluate_signature_accepts_only_context() -> None:
    parameters = list(signature(EMSPolicy.evaluate).parameters)

    assert parameters == ["self", "context"]


def test_evaluate_contract_uses_energy_context_and_decision_result() -> None:
    hints = get_type_hints(EMSPolicy.evaluate)

    assert hints["context"] is EnergySystemContext
    assert hints["return"] is DecisionResult


def test_return_contract_is_documented() -> None:
    documentation = EMSPolicy.evaluate.__doc__

    assert documentation is not None
    assert "DecisionResult" in documentation


def test_interface_has_no_instance_state() -> None:
    policy = EmptyEMSPolicy()

    assert EMSPolicy.__slots__ == ()
    assert not hasattr(policy, "__dict__")


def test_policy_evaluation_does_not_mutate_context() -> None:
    context = make_context()
    expected = make_context()
    assets = context.assets
    states = context.states
    power_flow = context.power_flow

    result = EmptyEMSPolicy().evaluate(context)

    assert result == DecisionResult.empty()
    assert context == expected
    assert context.assets is assets
    assert context.states is states
    assert context.power_flow is power_flow


def test_repeated_evaluation_is_deterministic() -> None:
    policy = EmptyEMSPolicy()
    context = make_context()

    assert policy.evaluate(context) == policy.evaluate(context)
