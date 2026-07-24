"""Tests for one deterministic EMS decision cycle."""

from dataclasses import FrozenInstanceError, fields
from typing import Any, cast

import pytest

from kernel.asset import BatteryAsset
from kernel.context import EnergySystemContext
from kernel.cycle import EMSCycle
from kernel.decision import DecisionResult
from kernel.execution import PolicyExecutor
from kernel.ids import AssetId
from kernel.policy import EMSPolicy
from kernel.power import PowerFlow
from kernel.state import BatteryState

EXPECTED_RESULT = DecisionResult.empty()
POLICY_ERROR = RuntimeError("policy failed")


class ReturningPolicy(EMSPolicy):
    __slots__ = ()

    def evaluate(self, context: EnergySystemContext) -> DecisionResult:
        return EXPECTED_RESULT


class RecordingPolicy(EMSPolicy):
    __slots__ = ("calls", "received_context")

    def __init__(self) -> None:
        self.calls = 0
        self.received_context: EnergySystemContext | None = None

    def evaluate(self, context: EnergySystemContext) -> DecisionResult:
        self.calls += 1
        self.received_context = context
        return EXPECTED_RESULT


class RaisingPolicy(EMSPolicy):
    __slots__ = ()

    def evaluate(self, context: EnergySystemContext) -> DecisionResult:
        raise POLICY_ERROR


class DirectEvaluationFailsPolicy(EMSPolicy):
    __slots__ = ()

    def evaluate(self, context: EnergySystemContext) -> DecisionResult:
        raise AssertionError("EMSCycle called policy.evaluate directly")


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


def test_creates_valid_cycle() -> None:
    cycle = EMSCycle.execute(ReturningPolicy(), make_context())

    assert isinstance(cycle, EMSCycle)
    assert cycle.result == DecisionResult.empty()


def test_preserves_exact_context_identity() -> None:
    context = make_context()

    cycle = EMSCycle.execute(ReturningPolicy(), context)

    assert cycle.context is context


def test_preserves_exact_result_identity() -> None:
    cycle = EMSCycle.execute(ReturningPolicy(), make_context())

    assert cycle.result is EXPECTED_RESULT


def test_policy_executes_once_with_exact_context() -> None:
    policy = RecordingPolicy()
    context = make_context()

    EMSCycle.execute(policy, context)

    assert policy.calls == 1
    assert policy.received_context is context


def test_execution_uses_policy_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = DirectEvaluationFailsPolicy()
    context = make_context()
    received: list[tuple[EMSPolicy, EnergySystemContext]] = []

    def fake_execute(
        supplied_policy: EMSPolicy,
        supplied_context: EnergySystemContext,
    ) -> DecisionResult:
        received.append((supplied_policy, supplied_context))
        return EXPECTED_RESULT

    monkeypatch.setattr(
        PolicyExecutor,
        "execute",
        staticmethod(fake_execute),
    )

    cycle = EMSCycle.execute(policy, context)

    assert received == [(policy, context)]
    assert cycle.result is EXPECTED_RESULT


def test_preserves_context_and_nested_objects() -> None:
    context = make_context()
    expected = make_context()
    assets = context.assets
    states = context.states
    power_flow = context.power_flow
    asset = context.assets[0]
    state = context.states[0]

    EMSCycle.execute(ReturningPolicy(), context)

    assert context == expected
    assert context.assets is assets
    assert context.states is states
    assert context.power_flow is power_flow
    assert context.assets[0] is asset
    assert context.states[0] is state


def test_cycle_is_frozen_and_slotted() -> None:
    cycle = EMSCycle.execute(ReturningPolicy(), make_context())

    assert not hasattr(cycle, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, cycle).result = DecisionResult.empty()


def test_cycle_contains_only_context_and_result() -> None:
    assert [field.name for field in fields(EMSCycle)] == [
        "context",
        "result",
    ]


def test_propagates_policy_exception_unchanged() -> None:
    with pytest.raises(RuntimeError) as raised:
        EMSCycle.execute(RaisingPolicy(), make_context())

    assert raised.value is POLICY_ERROR


def test_direct_construction_preserves_inputs() -> None:
    context = make_context()
    result = DecisionResult.empty()

    cycle = EMSCycle(context=context, result=result)

    assert cycle.context is context
    assert cycle.result is result


def test_rejects_invalid_context() -> None:
    with pytest.raises(TypeError, match="context"):
        EMSCycle(
            context=cast(EnergySystemContext, object()),
            result=DecisionResult.empty(),
        )


def test_rejects_invalid_result() -> None:
    with pytest.raises(TypeError, match="result"):
        EMSCycle(
            context=make_context(),
            result=cast(DecisionResult, object()),
        )
