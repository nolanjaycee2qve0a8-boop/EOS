"""Analytic planner selection tests; actual dynamics are in the fixed day run."""

from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from typing import cast

import pytest

from forecast import ForecastHorizon
from tests.integration.test_joint_mpc_adapter import _case, _forecasts
from tools.dynamic_constraint_probe import FactSegment, battery
from tools.joint_execution_contract import JointExecutionContext
from tools.joint_mpc_adapter import (
    NET_LOAD_BASELINE,
    PRICE_BASELINE,
    IssuedMPCForecast,
    IssuedMPCRequestStrategy,
    mpc_strategy,
)
from tools.joint_strategy_adapter import MPC, RequestStrategy, StrategyInput
from tools.pv_grid_charge_joint_probe import run_joint


def frames(pv: float, load: float, price: float) -> tuple[IssuedMPCForecast, ...]:
    return tuple(
        replace(
            f,
            horizon=ForecastHorizon(
                tuple(
                    replace(
                        p,
                        pv_power_kw=pv,
                        load_power_kw=load,
                        electricity_price_cny_per_kwh=price,
                    )
                    for p in f.horizon.points
                )
            ),
        )
        for f in _forecasts()
    )


def observed(soc: float = 0.5) -> StrategyInput:
    return StrategyInput.snapshot(
        3600,
        soc,
        FactSegment(0, 86400, 0.9, 0.2, True, True, 0.8),
        battery(),
        observed_at_s=3540,
        available_at_s=3570,
        max_observation_age_s=90,
    )


def test_default_and_explicit_price_planner_requests_match() -> None:
    forecasts = _forecasts()
    implicit = mpc_strategy(forecasts)
    explicit = mpc_strategy(forecasts, planner=PRICE_BASELINE)
    assert implicit.planner == explicit.planner == PRICE_BASELINE
    for hour in range(24):
        at = hour * 3600
        facts = replace(
            observed(), at_s=at, observed_at_s=at - 60, available_at_s=at - 30
        )
        assert implicit.evaluate(facts) == explicit.evaluate(facts)


@pytest.mark.parametrize("load,expected", [(1.25, -1.0), (1.5, -1.25)])
def test_high_price_load_prediction_changes_net_request(
    load: float, expected: float
) -> None:
    strategy = mpc_strategy(frames(0.25, load, 0.9), planner=NET_LOAD_BASELINE)
    # Independent formula: discharge (forecast load - forecast PV).
    assert strategy.evaluate(observed()) == pytest.approx(expected, abs=1e-9, rel=0)


@pytest.mark.parametrize("pv,expected", [(2.0, 1.0), (2.5, 1.5)])
def test_pv_prediction_changes_surplus_charge_request(
    pv: float, expected: float
) -> None:
    strategy = mpc_strategy(frames(pv, 1.0, 0.55), planner=NET_LOAD_BASELINE)
    assert strategy.evaluate(observed()) == pytest.approx(expected, abs=1e-9, rel=0)


@pytest.mark.parametrize(
    "pv,load,price,soc,expected",
    [
        (2, 1, 0.9, 0.5, 1),  # Existing PV-surplus priority even at high price.
        (0.25, 1.25, 0.3, 0.5, 3),  # Existing cheap-grid request.
        (0.25, 1.25, 0.55, 0.5, 0),
        (5, 0.9, 0.55, 0.5, 3),  # 4.1 kW candidate, existing PCS revision to 3.
        (2, 1, 0.55, 1, 0),  # Full SOC cannot accept further charging.
        (0.25, 1.25, 0.9, 0.2, 0),  # Hard minimum cannot discharge.
    ],
)
def test_existing_rules_and_physical_revision(
    pv: float, load: float, price: float, soc: float, expected: float
) -> None:
    strategy = mpc_strategy(frames(pv, load, price), planner=NET_LOAD_BASELINE)
    assert strategy.evaluate(observed(soc)) == pytest.approx(expected, abs=1e-9, rel=0)


@pytest.mark.parametrize("value", ["unknown", "", None, True, lambda: None])
def test_unknown_planner_is_rejected_at_both_public_entries(value: object) -> None:
    with pytest.raises(ValueError, match="unknown MPC planner"):
        mpc_strategy(_forecasts(), planner=cast(str, value))
    with pytest.raises(ValueError, match="unknown MPC planner"):
        IssuedMPCRequestStrategy(_forecasts(), planner=cast(str, value))


def test_choice_is_immutable_and_callback_spoof_is_still_rejected() -> None:
    strategy = mpc_strategy(_forecasts(), planner=NET_LOAD_BASELINE)
    with pytest.raises(FrozenInstanceError):
        strategy.planner = PRICE_BASELINE  # type: ignore[misc]
    with pytest.raises(ValueError, match="issued-forecast preflight"):
        RequestStrategy(MPC, lambda _: 3.0)


@pytest.mark.parametrize("planner", [PRICE_BASELINE, NET_LOAD_BASELINE])
def test_selection_does_not_bypass_issued_forecast_preflight(planner: str) -> None:
    f = _forecasts()
    with pytest.raises(ValueError, match="24 issued forecasts"):
        mpc_strategy(f[:-1], planner=planner)
    with pytest.raises(ValueError, match="schedule"):
        mpc_strategy((f[1], f[0], *f[2:]), planner=planner)
    with pytest.raises(ValueError, match="not available"):
        replace(f[0], available_at=f[0].decision_at + timedelta(seconds=1))
    with pytest.raises(ValueError, match="stale"):
        replace(f[0], generated_at=f[0].decision_at - timedelta(hours=2))
    with pytest.raises(ValueError, match="coverage"):
        replace(f[0], coverage_end=f[0].coverage_end + timedelta(seconds=1))


def test_net_load_observation_arrival_expiry_and_tick_contract() -> None:
    strategy = mpc_strategy(frames(0.25, 1.25, 0.9), planner=NET_LOAD_BASELINE)
    assert strategy.evaluate(replace(observed(), available_at_s=3601)) == 0
    assert strategy.evaluate(replace(observed(), available_at_s=3600)) == -1
    assert strategy.evaluate(replace(observed(), observed_at_s=3509)) == 0
    assert strategy.evaluate(replace(observed(), fact=None)) == 0
    with pytest.raises(ValueError, match="hourly"):
        strategy.evaluate(replace(observed(), at_s=3601))


def test_net_load_still_requires_matching_daily_context() -> None:
    strategy = mpc_strategy(_forecasts(), planner=NET_LOAD_BASELINE)
    with pytest.raises(ValueError, match="explicit daily context"):
        run_joint(_case(), mode="dynamic", physical_step_s=60, strategy=strategy)
    with pytest.raises(ValueError, match="context and selected strategy differ"):
        run_joint(
            _case(),
            mode="dynamic",
            physical_step_s=60,
            strategy=strategy,
            context=JointExecutionContext(),
        )
