"""Input isolation and analytic reporting checks; no full-day simulation here."""

import json
from dataclasses import asdict, replace
from datetime import timedelta
from pathlib import Path

import pytest

from forecast import ForecastHorizon
from tools.joint_execution_contract import START_UTC
from tools.joint_strategy_comparison import comparison_cases
from tools.mpc_load_bias_experiment import (
    compare,
    forecast_pair,
    run_experiment,
    validate_pair,
)
from tools.reserve_target_isolation_experiment import (
    GapSlice,
    build_cases,
    common_target_gap,
)


def test_only_96_load_predictions_change_and_all_clocks_are_fixed() -> None:
    a, b = forecast_pair()
    assert len(a) == len(b) == 24
    changes = 0
    for hour, (left, right) in enumerate(zip(a, b, strict=True)):
        decision = START_UTC + timedelta(hours=hour)
        for frame in (left, right):
            assert frame.decision_at == frame.available_at == decision
            assert frame.generated_at == decision - timedelta(minutes=5)
            assert frame.coverage_start == decision
            assert frame.coverage_end == decision + timedelta(hours=4)
        assert replace(right, horizon=left.horizon) == left
        for offset, (p, q) in enumerate(
            zip(left.horizon.points, right.horizon.points, strict=True)
        ):
            assert p.load_power_kw == 1.25
            assert q.load_power_kw == 1.5  # Hand calculated 1.25 * 120%.
            assert p.pv_power_kw == q.pv_power_kw == 0.25
            assert p.timestamp == q.timestamp == decision + timedelta(hours=offset)
            price = 0.3 if hour == 0 else 0.9 if hour == 1 else 0.55
            assert p.electricity_price_cny_per_kwh == price
            assert replace(q, load_power_kw=p.load_power_kw) == p
            changes += 1
    assert changes == 96
    assert b[-1].coverage_end == START_UTC + timedelta(hours=27)


@pytest.mark.parametrize("load", [1.49, 1.51])
def test_wrong_bias_rejected(load: float) -> None:
    a, b = forecast_pair()
    point = replace(b[0].horizon.points[0], load_power_kw=load)
    frame = replace(b[0], horizon=ForecastHorizon((point, *b[0].horizon.points[1:])))
    with pytest.raises(ValueError, match="only load"):
        validate_pair(a, (frame, *b[1:]))


@pytest.mark.parametrize(
    "field,value",
    [
        ("pv_power_kw", 0.3),
        ("electricity_price_cny_per_kwh", 0.31),
    ],
)
def test_other_forecast_value_rejected(field: str, value: float) -> None:
    a, b = forecast_pair()
    if field == "pv_power_kw":
        point = replace(b[0].horizon.points[0], pv_power_kw=value)
    else:
        assert field == "electricity_price_cny_per_kwh"
        point = replace(b[0].horizon.points[0], electricity_price_cny_per_kwh=value)
    frame = replace(b[0], horizon=ForecastHorizon((point, *b[0].horizon.points[1:])))
    with pytest.raises(ValueError, match="only load"):
        validate_pair(a, (frame, *b[1:]))


def test_legal_but_changed_generation_timestamp_rejected() -> None:
    a, b = forecast_pair()
    frame = replace(b[0], generated_at=b[0].generated_at - timedelta(seconds=1))
    with pytest.raises(ValueError, match="clock"):
        validate_pair(a, (frame, *b[1:]))


def test_truncated_or_swapped_baseline_rejected() -> None:
    a, b = forecast_pair()
    with pytest.raises(ValueError, match="original forecast"):
        validate_pair((a[1], a[0], *a[2:]), b)
    with pytest.raises(ValueError, match="frame count"):
        validate_pair(a, b[:-1])


def test_frozen_actual_case_still_has_original_B_goals_and_permission() -> None:
    source = json.dumps(
        {name: asdict(case) for name, case in comparison_cases().items()},
        sort_keys=True,
    ).encode()
    _, case = build_cases(source)  # Existing digest guard, no simulation.
    assert case.initial_soc == 0.5
    assert case.segments[-1].end == 86400
    assert all(
        f.reserve_target_soc == (0.8 if f.start < 64800 else 0.9) for f in case.segments
    )
    events = [
        (f.start, f.grid_charge_allowed)
        for i, f in enumerate(case.segments)
        if i == 0 or f.grid_charge_allowed != case.segments[i - 1].grid_charge_allowed
    ]
    assert events == [
        (0, True),
        (5400, False),
        (7200, True),
        (21600, False),
        (64800, True),
    ]


def test_common_gap_analytic_constant_soc_splits_at_target_change() -> None:
    result = common_target_gap((GapSlice(0, 86400, 0.5, 0.5),), 0.5)
    assert result == pytest.approx(
        {"terminal_kwh": 4, "peak_kwh": 4, "integral_kwh_h": 78}, abs=2.4e-7, rel=0
    )


def test_comparison_preserves_equal_results_and_inventory_tradeoff() -> None:
    a = {
        "net_cost_cny": 1.0,
        "final_inventory_kwh": 5.0,
        "prohibited_grid_charge_kwh": 0.1,
    }
    assert compare(a, a) == dict.fromkeys(a, 0.0)
    b = {**a, "net_cost_cny": 0.8, "final_inventory_kwh": 4.0}
    assert compare(a, b) == pytest.approx(
        {
            "net_cost_cny": -0.2,
            "final_inventory_kwh": -1.0,
            "prohibited_grid_charge_kwh": 0.0,
        }
    )


def test_existing_output_rejected_before_reading_input(tmp_path: Path) -> None:
    with pytest.raises(FileExistsError, match="never overwrite"):
        run_experiment(tmp_path / "missing.json", tmp_path)


def test_wrong_source_rejected_without_output_or_execution(tmp_path: Path) -> None:
    source = tmp_path / "wrong.json"
    source.write_text("{}", encoding="utf-8")
    output = tmp_path / "result"
    with pytest.raises(ValueError, match="SHA-256 differs"):
        run_experiment(source, output)
    assert not output.exists()
