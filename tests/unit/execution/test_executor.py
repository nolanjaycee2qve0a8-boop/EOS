"""Tests for stateless EMS policy execution."""

from dataclasses import FrozenInstanceError
from inspect import signature
from typing import Any, cast, get_type_hints

import pytest

from kernel.asset import BatteryAsset
from kernel.context import EnergySystemContext
from kernel.decision import DecisionResult
from kernel.execution import PolicyExecutor
from kernel.ids import AssetId
from kernel.policy import EMSPolicy
from kernel.power import PowerFlow
from kernel.state import BatteryState

FIRST_RESULT = DecisionResult.empty()
SECOND_RESULT = DecisionResult.empty()
POLICY_ERROR = RuntimeError("policy evaluation failed")


class FirstPolicy(EMSPolicy):
    __slots__ = ()

    def evaluate(self, context: EnergySystemContext) -> DecisionResult:
        return FIRST_RESULT


class SecondPolicy(EMSPolicy):
    __slots__ = ()

    def evaluate(self, context: EnergySystemContext) -> DecisionResult:
        return SECOND_RESULT


class RaisingPolicy(EMSPolicy):
    __slots__ = ()

    def evaluate(self, context: EnergySystemContext) -> DecisionResult:
        raise POLICY_ERROR


class InvalidResultPolicy(EMSPolicy):
    __slots__ = ()

    def evaluate(self, context: EnergySystemContext) -> DecisionResult:
        return cast(DecisionResult, object())


def make_context() -> EnergySystemContext:
    battery = BatteryAsset(
        asset_id=AssetId("battery-1"),
        name="Battery 1",
        capacity_kwh=10.0,
        max_charge_kw=5.0,
        max_discharge_kw=5.0,
    )
    state = BatteryState(
        asset_id=battery.asset_id,
        soc=0.5,
        power_kw=0.0,
    )
    power_flow = PowerFlow(
        pv_power_kw=0.0,
        load_power_kw=0.0,
        battery_power_kw=0.0,
        grid_power_kw=0.0,
    )
    return EnergySystemContext(
        assets=(battery,),
        states=(state,),
        power_flow=power_flow,
    )


def test_executes_policy_and_returns_exact_result() -> None:
    result = PolicyExecutor.execute(FirstPolicy(), make_context())

    assert result is FIRST_RESULT


def test_supports_policy_replacement_between_calls() -> None:
    executor = PolicyExecutor()
    context = make_context()

    first = executor.execute(FirstPolicy(), context)
    second = executor.execute(SecondPolicy(), context)

    assert first is FIRST_RESULT
    assert second is SECOND_RESULT
    assert first is not second


def test_preserves_immutable_context_and_nested_objects() -> None:
    context = make_context()
    expected = make_context()
    assets = context.assets
    states = context.states
    power_flow = context.power_flow
    asset = context.assets[0]
    state = context.states[0]

    PolicyExecutor.execute(FirstPolicy(), context)

    assert context == expected
    assert context.assets is assets
    assert context.states is states
    assert context.power_flow is power_flow
    assert context.assets[0] is asset
    assert context.states[0] is state


def test_context_remains_frozen_after_execution() -> None:
    context = make_context()
    PolicyExecutor.execute(FirstPolicy(), context)

    with pytest.raises(FrozenInstanceError):
        cast(Any, context).assets = ()


def test_propagates_policy_exception_unchanged() -> None:
    with pytest.raises(RuntimeError) as raised:
        PolicyExecutor.execute(RaisingPolicy(), make_context())

    assert raised.value is POLICY_ERROR


def test_rejects_invalid_policy() -> None:
    with pytest.raises(TypeError, match="policy"):
        PolicyExecutor.execute(cast(EMSPolicy, object()), make_context())


def test_rejects_invalid_context() -> None:
    with pytest.raises(TypeError, match="context"):
        PolicyExecutor.execute(
            FirstPolicy(),
            cast(EnergySystemContext, object()),
        )


def test_rejects_invalid_policy_result() -> None:
    with pytest.raises(TypeError, match="DecisionResult"):
        PolicyExecutor.execute(InvalidResultPolicy(), make_context())


def test_executor_is_stateless_and_does_not_own_policy() -> None:
    executor = PolicyExecutor()

    assert PolicyExecutor.__slots__ == ()
    assert not hasattr(executor, "__dict__")
    with pytest.raises(AttributeError):
        cast(Any, executor).policy = FirstPolicy()


def test_execute_contract_has_only_policy_and_context_parameters() -> None:
    assert list(signature(PolicyExecutor.execute).parameters) == [
        "policy",
        "context",
    ]


def test_execute_contract_annotations_are_explicit() -> None:
    hints = get_type_hints(PolicyExecutor.execute)

    assert hints == {
        "policy": EMSPolicy,
        "context": EnergySystemContext,
        "return": DecisionResult,
    }
