"""Interface acceptance without changing the two existing request policies."""

from dataclasses import FrozenInstanceError, asdict, replace
from typing import cast

import pytest

from tools.dynamic_constraint_probe import FactSegment, _request, battery
from tools.joint_execution_contract import JointExecutionContext, daily_case
from tools.joint_strategy_adapter import (
    BASIC,
    JOINT,
    RequestStrategy,
    StrategyInput,
    strategy_by_id,
)
from tools.pv_grid_charge_joint_probe import run_joint


def test_pcs_overrequest_minimal() -> None:
    """10:00 raw 4.1 kW is not 4.1 kW of executable AC absorption."""
    from tools.joint_strategy_comparison import run_strategy

    result = run_strategy(daily_case(), BASIC, mode="ideal", step_s=60)
    row = next(x for x in result.execution.ledger if x.start_s == 36000)
    assert row.original_request_kw == 4.1
    assert row.actual_battery_kw == 3
    assert row.constrained_request_kw == 3
    assert abs(row.delivered_pv_kw - 3.9) < 1e-9
    assert abs(row.grid_kw) < 1e-9


@pytest.mark.parametrize(
    "requested,limited", [(4.1, 3), (3, 3), (-4.1, -3), (-3, -3), (0, 0)]
)
def test_pcs_boundary_uses_executable_command(requested: float, limited: float) -> None:
    from tools.pv_curtailment_probe import _soc_boundary_seconds, pcs_limited_request

    params = battery()
    assert pcs_limited_request(requested, params) == limited
    duration = _soc_boundary_seconds(0.5, requested, params)
    if limited > 0:
        assert duration == (1 - 0.5) * 10 * 3600 / (limited * 0.95)
    elif limited < 0:
        assert duration == (0.5 - 0.2) * 10 * 0.95 * 3600 / -limited
    else:
        assert duration is None


@pytest.mark.parametrize("initial", [1.0, 0.999, 0.2001])
@pytest.mark.parametrize("mode", ["ideal", "dynamic"])
def test_capability_at_soc_boundaries_and_delayed_changes(
    initial: float, mode: str
) -> None:
    from tools.dynamic_constraint_probe import Case
    from tools.joint_daily_output import validate_ledger, window_totals
    from tools.joint_strategy_comparison import metric_tolerance, run_strategy

    # Same-time external/EMS/execution facts; a later half-hour revoke is NOT
    # another EMS decision. Surplus and deficit both exceed PCS capability.
    case = Case(
        "capability-edges",
        initial,
        (
            FactSegment(0, 3600, 5, 0, True, True, 0.2),
            FactSegment(3600, 5400, 0.9, 5, True, True, 0.2),
            FactSegment(5400, 7200, 0.9, 5, False, True, 0.2),
            FactSegment(7200, 86400, 0.8, 0, False, True, 0.2),
        ),
    )
    reference = None
    for step in (3600, 60, 15):
        result = run_strategy(case, BASIC, mode=mode, step_s=step)
        assert result.passed
        validate_ledger(result.execution.ledger)
        assert tuple(d.at for d in result.execution.decisions) == tuple(
            range(0, 86400, 3600)
        )
        assert all(abs(r.constrained_request_kw) <= 3 for r in result.execution.ledger)
        assert any(d.original_request_kw == 4.1 for d in result.execution.decisions)
        values = window_totals(result.execution.ledger, 0, 86400)
        if reference is not None:
            for key in values:
                assert abs(values[key] - reference[key]) <= metric_tolerance(key), key
        reference = values


def test_exact_soc_and_execution_boundary_keeps_event_order() -> None:
    from tools.dynamic_constraint_probe import Case
    from tools.joint_strategy_comparison import run_strategy

    # 3 kW AC charging for one hour reaches exactly full (including eta).
    case = Case(
        "same-time-full",
        1 - 3 * 0.95 / 10,
        (
            FactSegment(0, 3600, 0.9, 5, True, True, 0.2),
            FactSegment(3600, 86400, 0.9, 5, False, True, 0.2),
        ),
    )
    result = run_strategy(case, BASIC, mode="ideal", step_s=3600)
    decision = next(d for d in result.execution.decisions if d.at == 3600)
    assert abs(decision.feedback_soc - 1) < 1e-9
    row = next(r for r in result.execution.ledger if r.start_s == 3600)
    assert not row.grid_charge_allowed and not row.effective_permission
    assert abs(row.actual_battery_kw) < 1e-9
    assert abs(row.grid_kw) < 1e-9


def test_detached_readonly_input() -> None:
    fact = FactSegment(0, 3600, 1, 0, True, True, 0.8)
    params = battery()
    facts = StrategyInput.snapshot(0, 0.5, fact, params)
    assert facts.fact == fact and facts.fact is not fact
    assert facts.battery == params and facts.battery is not params
    for obj, key in (
        (facts, "soc"),
        (facts.fact, "pv_kw"),
        (facts.battery, "capacity_kwh"),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(obj, key, 0)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, None, "3", []])
def test_illegal_request_fails(value: object) -> None:
    strategy = RequestStrategy(JOINT, lambda _: cast(float, value))
    with pytest.raises(ValueError, match="finite numeric"):
        run_joint(
            daily_case(),
            mode="ideal",
            physical_step_s=3600,
            context=JointExecutionContext(),
            strategy=strategy,
        )


def test_strategy_error_propagates() -> None:
    def broken(_: StrategyInput) -> float:
        raise RuntimeError("policy failure")

    with pytest.raises(RuntimeError, match="policy failure"):
        run_joint(
            daily_case(),
            mode="ideal",
            physical_step_s=3600,
            context=JointExecutionContext(),
            strategy=RequestStrategy(JOINT, broken),
        )


def test_unknown_and_mismatched_identity_fail() -> None:
    with pytest.raises(ValueError, match="unknown"):
        strategy_by_id("unknown")
    with pytest.raises(ValueError, match="unknown"):
        RequestStrategy("unknown", lambda _: 0.0)
    with pytest.raises(ValueError, match="unknown"):
        JointExecutionContext(strategy="unknown")
    with pytest.raises(ValueError, match="differ"):
        run_joint(
            daily_case(),
            mode="ideal",
            physical_step_s=3600,
            context=JointExecutionContext(),
            strategy=strategy_by_id(BASIC),
        )
    with pytest.raises(ValueError, match="differ"):
        run_joint(
            daily_case(),
            mode="ideal",
            physical_step_s=3600,
            context=JointExecutionContext(strategy=BASIC),
        )


@pytest.mark.parametrize(
    "soc,allowed,pv,target",
    [
        (0.5, True, 0, 0.8),
        (0.5, False, 0, 0.8),
        (0.9, True, 0, 0.8),
        (0.5, False, 5.8, 0.2),
    ],
)
def test_reuse_request_rules(
    soc: float, allowed: bool, pv: float, target: float
) -> None:
    from ems_simulator.runner import DailySimulationRunner

    fact = FactSegment(0, 3600, 0.8, pv, allowed, True, target)
    facts = StrategyInput.snapshot(0, soc, fact, battery())
    assert strategy_by_id(JOINT).evaluate(facts) == _request(fact, soc, battery())
    assert strategy_by_id(BASIC).evaluate(
        facts
    ) == DailySimulationRunner._battery_request(pv, 0.8, soc, target)


@pytest.mark.parametrize("mode", ["ideal", "dynamic"])
@pytest.mark.parametrize("step", [3600, 60, 15])
def test_omitted_and_explicit_original_exact(mode: str, step: int) -> None:
    case = daily_case()
    default = run_joint(
        case, mode=mode, physical_step_s=step, context=JointExecutionContext()
    )
    explicit = run_joint(
        case,
        mode=mode,
        physical_step_s=step,
        context=JointExecutionContext(),
        strategy=strategy_by_id(JOINT),
    )
    assert asdict(default) == asdict(explicit)


@pytest.mark.parametrize("identifier", [JOINT, BASIC])
def test_24_calls_own_feedback_and_same_time_events(identifier: str) -> None:
    from tools.joint_strategy_comparison import comparison_cases

    calls: list[StrategyInput] = []
    original = strategy_by_id(identifier)

    def recording(facts: StrategyInput) -> float:
        calls.append(facts)
        return original.evaluate(facts)

    case = comparison_cases()["reserve"]
    result = run_joint(
        case,
        mode="dynamic",
        physical_step_s=3600,
        context=JointExecutionContext(strategy=identifier),
        strategy=RequestStrategy(identifier, recording),
    )
    assert [x.at_s for x in calls] == list(range(0, 86400, 3600))
    assert calls[0].soc == case.initial_soc
    assert [x.soc for x in calls] == [
        x.feedback_soc for x in result.execution.decisions
    ]
    for sample in calls:
        row = next(x for x in result.execution.ledger if x.start_s == sample.at_s)
        assert sample.soc == row.soc_before
    assert calls[2].fact.grid_charge_allowed
    assert not calls[6].fact.grid_charge_allowed
    assert calls[18].fact.reserve_target_soc == 0.9
    assert all(x.fact is not y for x in calls for y in case.segments)


def test_record_frequency_does_not_change_control_or_ledger() -> None:
    from tools.joint_strategy_comparison import run_strategy

    a = run_strategy(daily_case(), BASIC, mode="dynamic", step_s=60)
    b = run_strategy(
        daily_case(), BASIC, mode="dynamic", step_s=60, record_s=15, display_s=1
    )
    assert a == replace(b, execution=replace(b.execution, record_period_s=60))
