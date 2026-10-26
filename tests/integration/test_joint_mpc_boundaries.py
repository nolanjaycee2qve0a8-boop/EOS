"""Final MPC boundary regression, separate from the six sealed candidate files.

The six retired SOC cases assumed that MPC always requests PCS rated power.
They are replaced by six hourly-headroom MPC contracts and six fixed-request
executor contracts (charge/discharge times three physical steps). Original
failure and collection-error receipts remain outside the source worktree.
This final collection retains the other 53 cases, for 65 nodes total.

Oracle constants are frozen contract tolerances: P/S=1e-9 kW/fraction,
T=1e-7 s, interval E=2e-9 kWh, daily E=2.4e-8 kWh. No relative slack.
Forecast values are issued synthetic inputs, not future simulation truth.
Accounting oracles use P*seconds/3600 and eta=0.95, capacity=10 kWh.
The short accounting cases exercise the SAME executor directly with fixed
requests, while observation/day/forecast tests exercise the real MPC adapter.
No scheduler/pause-resume or source-authenticity capability is asserted.
"""

import random
from dataclasses import asdict, replace
from datetime import timedelta
from itertools import pairwise
from math import fsum
from pathlib import Path
from typing import Any, cast

import pytest

from capability import CapabilityDescriptor
from ems_strategy import EMSContext
from forecast import ForecastHorizon, ForecastPoint
from kernel.decision import DecisionContext
from objective import ObjectiveCapabilityActivationComposition
from tools.dynamic_constraint_probe import Case, FactSegment
from tools.joint_execution_contract import START_UTC, JointExecutionContext
from tools.joint_mpc_adapter import (
    IssuedMPCForecast,
    IssuedMPCRequestStrategy,
    mpc_strategy,
)
from tools.joint_strategy_adapter import (
    JOINT,
    MPC,
    RequestStrategy,
    StrategyInput,
    strategy_by_id,
)
from tools.pv_curtailment_probe import (
    CurtailmentResult,
    CurtailmentSettings,
    run_curtailment,
)
from tools.pv_grid_charge_joint_probe import JointResult, run_joint

P = S = 1e-9
T = 1e-7
E = 2e-9
EDAY = 2.4e-8


def eq(actual: float, expected: float, tol: float = E) -> None:
    assert actual == pytest.approx(expected, rel=0, abs=tol)


def forecasts(price: float = 0.3) -> tuple[IssuedMPCForecast, ...]:
    frames = []
    for hour in range(24):
        at = START_UTC + timedelta(hours=hour)
        horizon = ForecastHorizon(
            tuple(
                ForecastPoint(at + timedelta(hours=k), 0.25, 1.25, price)
                for k in range(4)
            )
        )
        frames.append(
            IssuedMPCForecast(
                at, at - timedelta(minutes=5), at, at, at + timedelta(hours=4), horizon
            )
        )
    return tuple(frames)


def day(initial: float = 0.5, load: float = 1.0, pv: float = 0.0) -> Case:
    return Case(
        "sealed-boundary", initial, (FactSegment(0, 86400, load, pv, True, True, 0.2),)
    )


def run_day(case: Case, price: float = 0.3, step: int = 60) -> JointResult:
    return run_joint(
        case,
        mode="dynamic",
        physical_step_s=step,
        context=JointExecutionContext(strategy=MPC),
        strategy=mpc_strategy(forecasts(price)),
    )


def conserved(execution: CurtailmentResult) -> None:
    rows = execution.ledger
    eq(rows[0].start_s, 0, T)
    eq(rows[-1].end_s, execution.settings.duration_seconds, T)
    for a, b in pairwise(rows):
        eq(a.end_s, b.start_s, T)
        eq(a.soc_after, b.soc_before, S)
    for row in rows:
        assert row.duration_s > 0
        assert 0.2 - S <= row.soc_after <= 1 + S
        assert abs(row.actual_battery_kw) <= 3 + P
        eq(
            row.delivered_pv_kwh + row.import_kwh - row.export_kwh,
            row.load_kwh + row.battery_kwh,
        )
        eq(row.available_pv_kwh, row.delivered_pv_kwh + row.curtailed_pv_kwh)
        eq(row.battery_kwh, row.storage_delta_kwh + row.conversion_loss_kwh)
        eq(row.storage_delta_kwh, 10 * (row.soc_after - row.soc_before))
    eq(
        fsum(r.storage_delta_kwh for r in rows),
        10 * (execution.final_soc - execution.case.initial_soc),
        EDAY,
    )


def test_module_sources_are_the_sealed_worktree() -> None:
    import tools.joint_mpc_adapter as adapter
    import tools.pv_curtailment_probe as executor

    expected = Path(__file__).resolve().parents[2]
    assert Path(adapter.__file__).resolve() == expected / "tools/joint_mpc_adapter.py"
    assert (
        Path(executor.__file__).resolve() == expected / "tools/pv_curtailment_probe.py"
    )


@pytest.mark.parametrize("available,expected", [(3599, 3.0), (3600, 3.0), (3601, 0.0)])
def test_observation_arrival_exact_boundary(available: int, expected: float) -> None:
    facts = StrategyInput.snapshot(
        3600,
        0.5,
        day().segments[0],
        JointExecutionContext().battery_parameters,
        observed_at_s=3570,
        available_at_s=available,
        max_observation_age_s=90,
    )
    eq(mpc_strategy(forecasts()).evaluate(facts), expected, P)


@pytest.mark.parametrize("sampled,expected", [(3510, 3.0), (3509, 0.0)])
def test_observation_age_exact_limit(sampled: int, expected: float) -> None:
    facts = StrategyInput.snapshot(
        3600,
        0.5,
        day().segments[0],
        JointExecutionContext().battery_parameters,
        observed_at_s=sampled,
        available_at_s=3600,
        max_observation_age_s=90,
    )
    eq(mpc_strategy(forecasts()).evaluate(facts), expected, P)


@pytest.mark.parametrize(
    "obs,delay,change,expected_pv",
    [(17, 59, 3523, 5), (17, 60, 3523, 5), (17, 61, 3523, 0), (0, 0, 3600, 5)],
)
def test_executor_arrival_before_at_after_hour_and_zero_delay(
    monkeypatch: pytest.MonkeyPatch,
    obs: int,
    delay: int,
    change: int,
    expected_pv: float,
) -> None:
    import tools.joint_mpc_adapter as module

    real = EMSContext
    captured: list[DecisionContext] = []

    def spy(
        context: DecisionContext,
        composition: ObjectiveCapabilityActivationComposition,
        capability: CapabilityDescriptor,
    ) -> EMSContext:
        captured.append(context)
        return real(context, composition, capability)

    monkeypatch.setattr(module, "EMSContext", spy)
    case = Case(
        "effect-boundary",
        0.5,
        (
            FactSegment(0, change, 1, 0, True, True, 0.2),
            FactSegment(change, 86400, 0.2, 5, True, True, 0.2),
        ),
    )
    settings = CurtailmentSettings(
        duration_seconds=86400,
        pv_ac_max_kw=6,
        observation_delay_s=obs,
        execution_delay_s=delay,
        strict_startup_observation=True,
        current_pv_surplus_guard=False,
        guard_controlled_pv_rise=True,
    )
    result = run_curtailment(
        case, physical_step_s=60, settings=settings, strategy=mpc_strategy(forecasts())
    )
    at_hour = next(c for c in captured if c.timestamp == START_UTC + timedelta(hours=1))
    eq(at_hour.pv_power_kw, expected_pv, P)
    eq(at_hour.load_power_kw, 0.2 if expected_pv else 1, P)
    at_next = next(c for c in captured if c.timestamp == START_UTC + timedelta(hours=2))
    eq(at_next.pv_power_kw, 5, P)
    assert tuple(d.at for d in result.decisions) == tuple(range(0, 86400, 3600))
    conserved(result)


def test_only_undelivered_future_facts_change_not_current_decision() -> None:
    # Change happens at t=3600. Latest delivered sample is t=3520;
    # the two executions have identical histories/SOC up to the decision.
    requests = []
    for pv, load in ((2, 0.8), (5, 0.2)):
        case = Case(
            "future-pair",
            0.5,
            (
                FactSegment(0, 3600, 1, 0, True, True, 0.2),
                FactSegment(3600, 86400, load, pv, True, True, 0.2),
            ),
        )
        result = run_day(case)
        requests.append(result.execution.decisions[1])
    assert requests[0] == requests[1]


@pytest.mark.parametrize(
    "field", ["pv_power_kw", "load_power_kw", "electricity_price_cny_per_kwh"]
)
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_forecast_rejected_at_artifact_boundary(
    field: str, value: float
) -> None:
    with pytest.raises(ValueError, match="finite"):
        replace(
            forecasts()[0].horizon.points[0], **cast(dict[str, Any], {field: value})
        )


@pytest.mark.parametrize("field", ["pv_power_kw", "load_power_kw"])
def test_missing_forecast_power_rejected(field: str) -> None:
    with pytest.raises(TypeError, match="number"):
        replace(forecasts()[0].horizon.points[0], **cast(dict[str, Any], {field: None}))


@pytest.mark.parametrize("length", [0, 3, 5])
def test_forecast_point_count_exactly_four(length: int) -> None:
    frame = forecasts()[0]
    points = tuple(
        ForecastPoint(START_UTC + timedelta(hours=i), 0, 1, 0.3) for i in range(length)
    )
    with pytest.raises(ValueError, match="exactly four"):
        replace(frame, horizon=ForecastHorizon(points))


def test_internal_forecast_time_gap_and_missing_price_rejected() -> None:
    frame = forecasts()[0]
    points = frame.horizon.points
    with pytest.raises(ValueError, match="hourly coverage"):
        replace(
            frame,
            horizon=ForecastHorizon(
                (
                    points[0],
                    replace(
                        points[1], timestamp=points[1].timestamp + timedelta(seconds=1)
                    ),
                    *points[2:],
                )
            ),
        )
    with pytest.raises(ValueError, match="requires each forecast price"):
        replace(
            frame,
            horizon=ForecastHorizon(
                (*points[:3], replace(points[3], electricity_price_cny_per_kwh=None))
            ),
        )


def test_forecast_age_and_generation_order_edges() -> None:
    frame = forecasts()[0]
    replace(frame, generated_at=START_UTC - timedelta(hours=1))
    with pytest.raises(ValueError, match="stale"):
        replace(frame, generated_at=START_UTC - timedelta(hours=1, seconds=1))
    with pytest.raises(ValueError, match="not available"):
        replace(
            frame, generated_at=START_UTC, available_at=START_UTC - timedelta(seconds=1)
        )
    # Signed finite synthetic prices are legal; do not reject negative prices.
    assert mpc_strategy(forecasts(-0.1)).identifier == MPC


@pytest.mark.parametrize("kind", ["missing", "mismatch", "duck"])
def test_entry_preconditions_fail_without_execution(kind: str) -> None:
    strategy = mpc_strategy(forecasts())
    context: JointExecutionContext | None = JointExecutionContext(strategy=MPC)

    class PretendMPC:
        identifier = MPC

        def evaluate(self, facts: StrategyInput) -> float:
            raise AssertionError("unvalidated callback executed")

    if kind == "missing":
        context = None
        error: type[Exception] = ValueError
        match = "explicit daily context"
    elif kind == "mismatch":
        context = JointExecutionContext()
        error, match = ValueError, "context and selected strategy differ"
    else:
        strategy = cast(IssuedMPCRequestStrategy, PretendMPC())
        error, match = TypeError, "validated request strategy"
    with pytest.raises(error, match=match):
        run_joint(
            day(),
            mode="dynamic",
            physical_step_s=60,
            context=context,
            strategy=strategy,
        )


def test_same_label_callback_and_wrong_control_period_rejected() -> None:
    with pytest.raises(ValueError, match="forecast preflight"):
        RequestStrategy(MPC, lambda _: 0)
    with pytest.raises(ValueError, match="hourly decisions"):
        run_curtailment(
            day(),
            physical_step_s=60,
            control_period_s=1800,
            settings=CurtailmentSettings(duration_seconds=86400),
            strategy=mpc_strategy(forecasts()),
        )


def test_next_day_requires_new_contract_not_implicit_resume() -> None:
    frames = forecasts()
    shifted = tuple(
        replace(
            f,
            decision_at=f.decision_at + timedelta(days=1),
            generated_at=f.generated_at + timedelta(days=1),
            available_at=f.available_at + timedelta(days=1),
            coverage_start=f.coverage_start + timedelta(days=1),
            coverage_end=f.coverage_end + timedelta(days=1),
            horizon=ForecastHorizon(
                tuple(
                    replace(p, timestamp=p.timestamp + timedelta(days=1))
                    for p in f.horizon.points
                )
            ),
        )
        for f in frames
    )
    with pytest.raises(ValueError, match="UTC decision hours"):
        mpc_strategy(shifted)
    with pytest.raises(ValueError, match="exactly 86400"):
        JointExecutionContext(duration_seconds=172800, strategy=MPC)


@pytest.mark.parametrize("step", [3600, 60, 15])
@pytest.mark.parametrize(
    "revoke,stop", [(3999, 4030), (4000, 4030), (4001, 4090), (7193, 7200)]
)
def test_permission_step_and_unsettled_tail_have_exact_energy(
    step: int, revoke: int, stop: int
) -> None:
    # Check samples check_at-20 and becomes effective check_at+10.
    # 3999/4000 -> check4020/effect4030; 4001 -> check4080/effect4090.
    # 7193 has no delivered observation before the 7200 endpoint: keep 7 s.
    case = Case(
        "permission-account",
        0.2,
        (
            FactSegment(0, revoke, 1, 0, True, True, 0.2),
            FactSegment(revoke, 7200, 1, 0, False, True, 0.2),
        ),
    )
    result = run_joint(
        case,
        mode="dynamic",
        physical_step_s=step,
        strategy=RequestStrategy(JOINT, lambda _: 3.0),
    )
    violations = [v for v in result.excursions if v.kind == "GRID_CHARGE_FORBIDDEN"]
    assert len(violations) == 1
    v = violations[0]
    eq(v.start_s, revoke, T)
    eq(v.end_s, stop, T)
    eq(v.duration_s, stop - revoke, T)
    eq(v.peak_kw, 3, P)
    eq(v.energy_kwh, 3 * (stop - revoke) / 3600)
    eq(
        fsum(r.prohibited_grid_charge_kwh for r in result.execution.ledger),
        3 * (stop - revoke) / 3600,
    )
    assert v.within_budget
    conserved(result.execution)


@pytest.mark.parametrize("step", [3600, 60, 15])
def test_import_export_sign_reversal_and_seven_second_tail(step: int) -> None:
    case = Case(
        "bidirectional-analytic",
        0.5,
        (
            FactSegment(0, 3599, 3, 2, True, False, 0.2),
            FactSegment(3599, 7193, 1, 2, True, False, 0.2),
            FactSegment(7193, 7200, 4, 2, True, False, 0.2),
        ),
    )
    result = run_joint(
        case,
        mode="ideal",
        physical_step_s=step,
        strategy=RequestStrategy(JOINT, lambda _: 0.0),
    )
    rows = result.execution.ledger
    eq(fsum(r.import_kwh for r in rows), (3599 + 2 * 7) / 3600)
    eq(fsum(r.export_kwh for r in rows), (7193 - 3599) / 3600)
    eq(result.execution.final_soc, 0.5, S)
    assert not result.excursions  # Zero Export is explicitly off.
    conserved(result.execution)


@pytest.mark.parametrize("step", [3600, 60, 15])
def test_dynamic_export_two_power_segments_and_day_tail(step: int) -> None:
    case = Case(
        "export-analytic",
        1.0,
        (
            FactSegment(0, 3599, 2, 2, True, True, 0.2),
            FactSegment(3599, 7200, 0.5, 2, True, True, 0.2),
        ),
    )
    result = run_joint(
        case,
        mode="dynamic",
        physical_step_s=step,
        strategy=RequestStrategy(JOINT, lambda _: 0.0),
    )
    events = [v for v in result.excursions if v.kind == "ZERO_EXPORT"]
    assert len(events) == 1
    v = events[0]
    # sample3640/check3660/effect3670; 1 kW/s staircase lowers at3671,3672.
    eq(v.start_s, 3599, T)
    eq(v.end_s, 3672, T)
    eq(v.duration_s, 73, T)
    eq(v.peak_kw, 1.5, P)
    eq(v.energy_kwh, (1.5 * 72 + 0.5) / 3600)
    assert v.within_budget
    conserved(result.execution)


def test_day_end_retains_unsettled_export_not_next_day_decision() -> None:
    case = Case(
        "day-tail",
        0.2,
        (
            FactSegment(0, 86393, 2, 2, True, True, 0.2),
            FactSegment(86393, 86400, 0.5, 2, True, True, 0.2),
        ),
    )
    result = run_day(case, price=0.9)
    events = [v for v in result.excursions if v.kind == "ZERO_EXPORT"]
    assert len(events) == 1
    eq(events[0].start_s, 86393, T)
    eq(events[0].end_s, 86400, T)
    eq(events[0].duration_s, 7, T)
    eq(events[0].peak_kw, 1.5, P)
    eq(events[0].energy_kwh, 1.5 * 7 / 3600)
    assert len(result.execution.decisions) == 24
    assert result.execution.decisions[-1].at == 82800
    conserved(result.execution)


def test_deterministic_repeat_resets_day_and_preserves_sealed_inputs() -> None:
    rng = random.Random(20261022)
    load = round(rng.uniform(0.8, 1.2), 6)
    case = day(load=load)
    before = asdict(case)
    strategy = mpc_strategy(forecasts())
    a = run_joint(
        case,
        mode="dynamic",
        physical_step_s=60,
        context=JointExecutionContext(strategy=MPC),
        strategy=strategy,
    )
    b = run_joint(
        case,
        mode="dynamic",
        physical_step_s=60,
        context=JointExecutionContext(strategy=MPC),
        strategy=strategy,
    )
    assert a == b
    assert asdict(case) == before
    assert tuple(d.at for d in a.execution.decisions) == tuple(range(0, 86400, 3600))
    conserved(a.execution)


def test_default_and_explicit_legacy_policy_still_identical() -> None:
    case = Case(
        "legacy-compat",
        0.5,
        (
            FactSegment(0, 3501, 1, 0, True, True, 0.8),
            FactSegment(3501, 7200, 0.8, 4, False, True, 0.8),
        ),
    )
    a = run_joint(case, mode="dynamic", physical_step_s=60)
    b = run_joint(
        case, mode="dynamic", physical_step_s=60, strategy=strategy_by_id(JOINT)
    )
    assert a == b


@pytest.mark.parametrize(
    "initial,price,target,energy",
    [(0.9999, 0.3, 1.0, 0.001 / 0.95), (0.2001, 0.9, 0.2, -0.001 * 0.95)],
)
@pytest.mark.parametrize("step", [3600, 60, 15])
def test_mpc_hourly_headroom_request_and_total_energy(
    step: int, initial: float, price: float, target: float, energy: float
) -> None:
    result = run_day(day(initial, load=3), price=price, step=step)
    execution = result.execution
    active = [r for r in execution.ledger if abs(r.actual_battery_kw) > P]
    assert active
    # One-hour AC power in kW numerically equals that hour's AC energy in kWh.
    eq(execution.decisions[1].original_request_kw, energy, P)
    eq(active[0].start_s, 3600, T)
    eq(active[-1].end_s, 7200, T)
    eq(fsum(r.battery_kwh for r in execution.ledger), energy)
    eq(execution.final_soc, target, S)
    conserved(execution)


@pytest.mark.parametrize(
    "initial,requested_kw,target,energy,seconds",
    [
        (0.9999, 3.0, 1.0, 0.001 / 0.95, (0.001 / 0.95) * 3600 / 3),
        (0.2001, -3.0, 0.2, -0.001 * 0.95, 0.001 * 0.95 * 3600 / 3),
    ],
)
@pytest.mark.parametrize("step", [3600, 60, 15])
def test_fixed_request_executor_reaches_soc_in_analytic_seconds(
    step: int,
    initial: float,
    requested_kw: float,
    target: float,
    energy: float,
    seconds: float,
) -> None:
    case = Case(
        "fixed-power-boundary", initial, (FactSegment(0, 7200, 3, 0, True, True, 0.2),)
    )
    result = run_joint(
        case,
        mode="dynamic",
        physical_step_s=step,
        strategy=RequestStrategy(JOINT, lambda _: requested_kw),
    )
    # Strict startup: check at60 samples40 and becomes effective at70.
    rows = result.execution.ledger
    active = [r for r in rows if abs(r.actual_battery_kw) > P]
    assert active
    eq(active[0].start_s, 70, T)
    eq(active[-1].end_s, 70 + seconds, T)
    eq(fsum(r.battery_kwh for r in rows), energy)
    eq(result.execution.final_soc, target, S)
    assert all(
        abs(r.actual_battery_kw) <= P for r in rows if r.start_s > 70 + seconds + T
    )
    conserved(result.execution)
