"""Issued-forecast MPC uses the original joint executor and physical ledger."""

from dataclasses import replace
from datetime import timedelta, timezone

import pytest

from capability import CapabilityDescriptor
from ems_strategy import EMSContext
from forecast import ForecastHorizon, ForecastPoint
from kernel.decision import DecisionContext
from objective import ObjectiveCapabilityActivationComposition
from tools.dynamic_constraint_probe import Case, FactSegment
from tools.joint_daily_output import validate_ledger, window_totals
from tools.joint_execution_contract import (
    DAY_ENERGY_TOL,
    START_UTC,
    JointExecutionContext,
)
from tools.joint_mpc_adapter import IssuedMPCForecast, mpc_strategy
from tools.joint_strategy_adapter import MPC, RequestStrategy, StrategyInput
from tools.pv_curtailment_probe import CurtailmentSettings, run_curtailment
from tools.pv_grid_charge_joint_probe import JointResult, run_joint


def _forecasts(
    first_price: float = 0.3, second_price: float = 0.9
) -> tuple[IssuedMPCForecast, ...]:
    frames = []
    for hour in range(24):
        decision = START_UTC + timedelta(hours=hour)
        price = first_price if hour == 0 else second_price if hour == 1 else 0.55
        horizon = ForecastHorizon(
            tuple(
                ForecastPoint(
                    decision + timedelta(hours=offset),
                    0.25,  # Caller-issued synthetic forecast, not future case PV.
                    1.25,  # Deliberately distinct from actual case load.
                    price,
                )
                for offset in range(4)
            )
        )
        frames.append(
            IssuedMPCForecast(
                decision,
                decision - timedelta(minutes=5),
                decision,
                decision,
                decision + timedelta(hours=4),
                horizon,
            )
        )
    return tuple(frames)


def _case(initial_soc: float = 0.5) -> Case:
    return Case(
        "issued-forecast-mpc",
        initial_soc,
        (
            FactSegment(0, 1800, 1, 0, True, True, 0.2),
            FactSegment(1800, 1860, 1, 0, False, True, 0.2),
            FactSegment(1860, 1920, 1, 5, False, True, 0.2),
            FactSegment(1920, 86400, 0.5, 5, False, True, 0.2),
        ),
    )


def _run(case: Case, *, price: float = 0.3, second_price: float = 0.9) -> JointResult:
    return run_joint(
        case,
        mode="dynamic",
        physical_step_s=3600,
        context=JointExecutionContext(strategy=MPC),
        strategy=mpc_strategy(_forecasts(price, second_price)),
    )


def test_forecast_preflight_fails_closed_before_execution() -> None:
    frames = _forecasts()
    with pytest.raises(ValueError, match="exactly 24"):
        mpc_strategy(frames[:-1])
    with pytest.raises(ValueError, match="stale"):
        replace(frames[0], generated_at=START_UTC - timedelta(hours=2))
    with pytest.raises(ValueError, match="not available"):
        replace(frames[0], available_at=START_UTC + timedelta(seconds=1))
    with pytest.raises(ValueError, match="coverage"):
        replace(frames[0], coverage_end=START_UTC + timedelta(hours=3))
    with pytest.raises(ValueError, match="hourly coverage"):
        replace(
            frames[0],
            horizon=ForecastHorizon(
                (
                    replace(
                        frames[0].horizon.points[0],
                        timestamp=START_UTC + timedelta(seconds=1),
                    ),
                    *frames[0].horizon.points[1:],
                )
            ),
        )
    with pytest.raises(ValueError, match="requires each forecast price"):
        replace(
            frames[0],
            horizon=ForecastHorizon(
                (
                    replace(
                        frames[0].horizon.points[0],
                        electricity_price_cny_per_kwh=None,
                    ),
                    *frames[0].horizon.points[1:],
                )
            ),
        )
    with pytest.raises(ValueError, match="schedule"):
        mpc_strategy((frames[1], frames[0], *frames[2:]))
    with pytest.raises(TypeError, match="timezone-aware"):
        replace(frames[0], generated_at=START_UTC.replace(tzinfo=None))


def test_mpc_cannot_use_an_unvalidated_callback_or_short_scenario() -> None:
    with pytest.raises(ValueError, match="forecast preflight"):
        RequestStrategy(MPC, lambda _: 0.0)
    short = Case(
        "short",
        0.5,
        (FactSegment(0, 7200, 1, 0, True, True, 0.2),),
    )
    with pytest.raises(ValueError, match="daily context"):
        run_joint(
            short,
            mode="dynamic",
            physical_step_s=3600,
            strategy=mpc_strategy(_forecasts()),
        )
    with pytest.raises(ValueError, match="facts must cover scenario duration"):
        run_joint(
            short,
            mode="dynamic",
            physical_step_s=3600,
            context=JointExecutionContext(strategy=MPC),
            strategy=mpc_strategy(_forecasts()),
        )
    with pytest.raises(ValueError, match="daily context and hourly decisions"):
        run_curtailment(
            short,
            physical_step_s=3600,
            settings=CurtailmentSettings(duration_seconds=7200),
            strategy=mpc_strategy(_forecasts()),
        )


def test_mpc_decision_uses_only_mature_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tools.joint_mpc_adapter as adapter

    contexts: list[DecisionContext] = []
    original = EMSContext

    def recording_context(
        source_context: DecisionContext,
        objective_composition: ObjectiveCapabilityActivationComposition,
        capability: CapabilityDescriptor,
    ) -> EMSContext:
        contexts.append(source_context)
        return original(source_context, objective_composition, capability)

    monkeypatch.setattr(adapter, "EMSContext", recording_context)
    case = Case(
        "hourly-truth-change",
        0.5,
        (
            FactSegment(0, 3600, 1, 0, True, True, 0.2),
            FactSegment(3600, 86400, 0.2, 5, True, True, 0.2),
        ),
    )
    result = _run(case)
    assert tuple(item.at for item in result.execution.decisions) == tuple(
        range(0, 86400, 3600)
    )
    # At t=0 nothing has arrived. At t=3600 the t=3600 change has not passed
    # the 20 s observation age and 10 s execution delay; by t=7200 it has.
    assert result.execution.decisions[0].original_request_kw == 0
    assert contexts[0].timestamp == START_UTC + timedelta(hours=1)
    assert contexts[0].pv_power_kw == 0
    assert contexts[0].load_power_kw == 1
    assert contexts[1].timestamp == START_UTC + timedelta(hours=2)
    assert contexts[1].pv_power_kw == 5
    assert contexts[1].load_power_kw == 0.2


def test_missing_or_stale_mpc_observation_fails_closed() -> None:
    strategy = mpc_strategy(_forecasts())
    fact = FactSegment(0, 86400, 1, 5, True, True, 0.2)
    for observed_at, available_at in (
        (None, None),
        (3500, 3550),  # 100 s old exceeds the independently set 90-s limit.
        (3580, 3601),  # Measurement exists but has not arrived.
        (3601, 3601),  # Future measurement cannot be used.
    ):
        facts = StrategyInput.snapshot(
            3600,
            0.5,
            fact,
            JointExecutionContext().battery_parameters,
            observed_at_s=observed_at,
            available_at_s=available_at,
            max_observation_age_s=90,
        )
        assert strategy.evaluate(facts) == 0


def test_existing_mpc_request_flows_through_dynamic_interlocks() -> None:
    result = _run(_case())
    execution = result.execution
    assert tuple(item.at for item in execution.decisions) == tuple(
        range(0, 86400, 3600)
    )
    assert execution.decisions[0].original_request_kw == 0
    assert execution.decisions[1].original_request_kw < 0
    validate_ledger(execution.ledger)
    assert execution.ledger[0].constrained_request_kw == 0  # No mature observation.
    assert execution.ledger[0].actual_battery_kw == 0
    assert all(
        row.constrained_request_kw <= 0
        for row in execution.ledger
        if row.start_s >= 3600
    )
    assert sum(row.prohibited_grid_charge_kwh for row in execution.ledger) == 0
    assert all(0.2 - 1e-9 <= row.soc_after <= 1 + 1e-9 for row in execution.ledger)
    assert all(abs(row.actual_battery_kw) <= 3 + 1e-9 for row in execution.ledger)
    assert all(item.within_budget for item in result.excursions)
    assert sum(row.export_kwh for row in execution.ledger) > 0
    assert all(
        row.prohibited_grid_charge_kwh == 0
        for row in execution.ledger
        if row.start_s >= 1900
    )
    export = tuple(item for item in result.excursions if item.kind == "ZERO_EXPORT")
    assert len(export) == 1
    assert export[0].start_s == pytest.approx(1920)
    assert export[0].duration_s == pytest.approx(71)
    assert export[0].peak_kw == pytest.approx(0.5)
    assert export[0].energy_kwh == pytest.approx(0.5 * 71 / 3600)


def test_delayed_permission_revoke_retains_bounded_violation_energy() -> None:
    # t=4000 revokes permission; the t=4020 check samples that fact and its
    # effect arrives at t=4030. The 3-kW request therefore has 30 s of
    # separately recorded prohibited charging, not a zeroed/hidden result.
    case = Case(
        "hourly-charge-revoke",
        0.5,
        (
            FactSegment(0, 4000, 1, 0, True, True, 0.2),
            FactSegment(4000, 86400, 1, 0, False, True, 0.2),
        ),
    )
    result = _run(case, second_price=0.3)
    assert result.execution.decisions[1].at == 3600
    assert result.execution.decisions[1].original_request_kw == pytest.approx(3)
    violations = tuple(
        item for item in result.excursions if item.kind == "GRID_CHARGE_FORBIDDEN"
    )
    assert len(violations) == 1
    assert violations[0].start_s == pytest.approx(4000)
    assert violations[0].end_s == pytest.approx(4030)
    assert violations[0].duration_s == pytest.approx(30)
    assert violations[0].peak_kw == pytest.approx(3)
    assert violations[0].energy_kwh == pytest.approx(3 * 30 / 3600)
    assert violations[0].within_budget
    assert sum(
        row.prohibited_grid_charge_kwh for row in result.execution.ledger
    ) == pytest.approx(3 * 30 / 3600)
    assert all(
        row.prohibited_grid_charge_kwh == 0
        for row in result.execution.ledger
        if row.start_s >= 4030
    )


@pytest.mark.parametrize("initial,price", [(1.0, 0.3), (0.2, 0.9)])
def test_mpc_respects_initial_hard_soc_boundaries(initial: float, price: float) -> None:
    result = _run(_case(initial), price=price)
    validate_ledger(result.execution.ledger)
    assert result.execution.decisions[0].original_request_kw == 0
    first_observed = result.execution.decisions[1].original_request_kw
    assert first_observed <= 0 if initial == 1.0 else first_observed >= 0
    assert all(
        0.2 - 1e-9 <= row.soc_after <= 1 + 1e-9 for row in result.execution.ledger
    )
    assert tuple(item.at for item in result.execution.decisions) == tuple(
        range(0, 86400, 3600)
    )


def test_mpc_charging_reaches_upper_soc_boundary_without_extra_energy() -> None:
    case = Case(
        "upper-boundary",
        0.9,
        (FactSegment(0, 86400, 1, 0, True, True, 0.2),),
    )
    result = _run(case, second_price=0.3)
    rows = result.execution.ledger
    validate_ledger(rows)
    assert result.execution.decisions[1].original_request_kw > 0
    assert result.execution.decisions[2].feedback_soc == pytest.approx(1)
    assert any("SOC_HARD_BOUNDARY" in row.restriction_reasons for row in rows)
    assert max(row.soc_after for row in rows) <= 1 + 1e-9
    assert all(
        row.actual_battery_kw == 0
        for row in rows
        if row.start_s >= 7200 and row.soc_before >= 1 - 1e-9
    )


def test_forecast_clock_accepts_explicit_utc_offset() -> None:
    frames = _forecasts()
    east = timezone(timedelta(hours=8))
    offset_frame = replace(
        frames[0], decision_at=frames[0].decision_at.astimezone(east)
    )
    assert mpc_strategy((offset_frame, *frames[1:])).identifier == MPC


def test_issued_price_changes_request_without_changing_actual_case() -> None:
    case = _case()
    charge = _run(case, second_price=0.3)
    discharge = _run(case, second_price=0.9)
    assert charge.execution.decisions[0].original_request_kw == 0
    assert discharge.execution.decisions[0].original_request_kw == 0
    assert charge.execution.decisions[1].original_request_kw > 0
    assert discharge.execution.decisions[1].original_request_kw < 0
    assert charge.execution.case is case and discharge.execution.case is case


def test_physical_and_display_cadence_do_not_create_mpc_decisions() -> None:
    case = _case()
    strategy = mpc_strategy(_forecasts())
    totals = []
    for physical_step, display_period in ((3600, 5), (60, 120), (15, 5)):
        result = run_joint(
            case,
            mode="dynamic",
            physical_step_s=physical_step,
            display_period_s=display_period,
            context=JointExecutionContext(strategy=MPC),
            strategy=strategy,
        )
        validate_ledger(result.execution.ledger)
        assert tuple(item.at for item in result.execution.decisions) == tuple(
            range(0, 86400, 3600)
        )
        totals.append(window_totals(result.execution.ledger, 0, 86400))
    for value in totals[1:]:
        for key, expected in totals[0].items():
            assert value[key] == pytest.approx(expected, abs=DAY_ENERGY_TOL), key
