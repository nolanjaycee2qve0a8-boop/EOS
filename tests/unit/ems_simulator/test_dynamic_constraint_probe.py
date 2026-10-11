"""Predeclared dynamic-constraint acceptance of the independent probe."""

from dataclasses import replace
from math import isclose

import pytest

from tools.dynamic_constraint_probe import (
    DURATION_SECONDS,
    Case,
    ProbeResult,
    _zero_export_assessment,
    cases,
    run_probe,
)

ENERGY_TOLERANCE = 8e-11
POWER_TOLERANCE = 1e-10
SOC_TOLERANCE = 1e-9


def _totals(result: ProbeResult) -> tuple[float, ...]:
    rows = result.ledger
    return (
        result.final_soc,
        sum(row.load_kwh for row in rows),
        sum(row.pv_kwh for row in rows),
        sum(row.battery_kwh for row in rows),
        sum(row.import_kwh for row in rows),
        sum(row.export_kwh for row in rows),
        sum(row.grid_to_battery_kwh for row in rows),
        sum(row.conversion_loss_kwh for row in rows),
    )


@pytest.mark.parametrize("case_name", tuple(cases()))
def test_predeclared_physics_and_step_comparison(case_name: str) -> None:
    case = cases()[case_name]
    results = [run_probe(case, physical_step=step) for step in (3600.0, 60.0, 15.0)]
    baseline = _totals(results[0])
    for result in results:
        assert [item.time for item in result.decisions] == [0, 3600]
        assert len(result.decisions) == 2
        assert result.ledger[0].start == 0
        assert result.ledger[-1].end == DURATION_SECONDS
        for previous, current in zip(result.ledger, result.ledger[1:], strict=False):
            assert abs(previous.end - current.start) <= 1e-9
        for row in result.ledger:
            hours = (row.end - row.start) / 3600
            assert row.end > row.start
            assert 0.2 - SOC_TOLERANCE <= row.soc_after <= 1 + SOC_TOLERANCE
            assert abs(row.actual_kw) <= 3 + POWER_TOLERANCE
            assert (
                abs(row.grid_kw - (row.load_kw + row.actual_kw - row.pv_kw))
                <= POWER_TOLERANCE
            )
            assert abs(
                row.load_kwh
                + row.battery_kwh
                - row.pv_kwh
                - row.import_kwh
                + row.export_kwh
            ) <= 4e-11 * max(hours, 1 / 3600)
            expected_storage = (
                row.battery_kwh * 0.95
                if row.battery_kwh > 0
                else row.battery_kwh / 0.95
            )
            assert abs(row.storage_delta_kwh - expected_storage) <= 4e-11 * max(
                hours, 1 / 3600
            )
            assert row.conversion_loss_kwh >= -ENERGY_TOLERANCE
            assert abs(
                row.conversion_loss_kwh - (row.battery_kwh - row.storage_delta_kwh)
            ) <= 4e-11 * max(hours, 1 / 3600)
            expected_grid_charge_kw = max(
                0.0, row.actual_kw - max(row.pv_kw - row.load_kw, 0.0)
            )
            assert abs(
                row.grid_to_battery_kwh - expected_grid_charge_kw * hours
            ) <= 4e-11 * max(hours, 1 / 3600)
            assert row.grid_to_battery_kwh <= row.import_kwh + ENERGY_TOLERANCE
            assert row.prohibited_grid_charge_kwh == (
                row.grid_to_battery_kwh if not row.grid_charge_allowed else 0.0
            )
            assert row.curtailment_kwh == 0
            assert row.unserved_load_kwh == 0
            for fact in case.segments:
                assert not (row.start < fact.start < row.end)
                assert not (row.start < fact.end < row.end)
            assert not (row.start < 3600 < row.end)
        for index, (actual, expected) in enumerate(
            zip(_totals(result), baseline, strict=True)
        ):
            tolerance = SOC_TOLERANCE if index == 0 else ENERGY_TOLERANCE
            assert abs(actual - expected) <= tolerance


def test_zero_export_pass_and_explicit_infeasibilities() -> None:
    scenarios = cases()
    steady = run_probe(scenarios["steady_zero_export"], physical_step=60)
    assert steady.export_violation_kwh == 0
    assert steady.export_peak_kw == 0
    assert steady.export_duration_s == 0
    expected_export = {
        "pv_jump": (2.5, 5.0, 1800.0),
        "load_drop": (1.5, 3.0, 1800.0),
        "full_battery": (8.0, 4.0, 7200.0),
    }
    for name, (energy, peak, duration) in expected_export.items():
        result = run_probe(scenarios[name], physical_step=60)
        assert isclose(result.export_violation_kwh, energy, abs_tol=ENERGY_TOLERANCE)
        assert isclose(result.export_peak_kw, peak, abs_tol=POWER_TOLERANCE)
        assert isclose(result.export_duration_s, duration, abs_tol=1e-9)
        assert all(row.curtailment_kwh == 0 for row in result.ledger)
    full = run_probe(scenarios["full_battery"], physical_step=60)
    assert all(row.actual_kw == 0 for row in full.ledger)
    assert full.export_peak_kw == 4
    assert _zero_export_assessment(steady) == ("PASS", "NONE")
    assert _zero_export_assessment(
        run_probe(scenarios["pv_jump"], physical_step=60)
    ) == ("FAIL_CONTROL_DELAY", "HELD_REQUEST_AFTER_EVENT")
    assert _zero_export_assessment(full) == (
        "FAIL_UNSUPPORTED",
        "FULL_SOC_NO_CURTAILMENT",
    )
    assert _zero_export_assessment(
        run_probe(scenarios["permission_mid_tick"], physical_step=60)
    ) == ("NOT_APPLICABLE", "NOT_ENABLED")


def test_soc_floor_splits_and_reserve_target_is_soft() -> None:
    floor = run_probe(cases()["soc_floor"], physical_step=3600)
    assert any(0 < row.end < 3600 and row.soc_after == 0.2 for row in floor.ledger)
    assert all(row.soc_after >= 0.2 - SOC_TOLERANCE for row in floor.ledger)
    assert any(row.actual_kw == 0 and row.grid_kw == 3 for row in floor.ledger)
    changed = run_probe(cases()["target_switch"], physical_step=60)
    assert changed.decisions[0].request_kw == -1
    assert changed.decisions[1].request_kw == 3
    assert changed.ledger[-1].target_gap_kwh_end > 0
    assert any(
        row.start >= 1800 and row.end <= 3600 and row.soc_after < row.reserve_target_soc
        for row in changed.ledger
    )


def test_grid_charge_permission_reports_mid_tick_violation_not_load_import() -> None:
    mid = run_probe(cases()["permission_mid_tick"], physical_step=60)
    on_tick = run_probe(cases()["permission_on_tick"], physical_step=60)
    assert isclose(mid.prohibited_grid_charge_kwh, 1.5, abs_tol=ENERGY_TOLERANCE)
    assert on_tick.prohibited_grid_charge_kwh == 0
    assert any(row.import_kwh > 0 for row in on_tick.ledger if row.start >= 3600)
    assert all(
        row.grid_to_battery_kwh == 0 for row in on_tick.ledger if row.start >= 3600
    )


def test_simultaneous_event_is_one_split_not_a_decision() -> None:
    result = run_probe(cases()["simultaneous"], physical_step=3600)
    assert [item.time for item in result.decisions] == [0, 3600]
    assert any(row.end == 1800 for row in result.ledger)
    assert any(row.start == 1800 for row in result.ledger)
    assert all(not (row.start < 1800 < row.end) for row in result.ledger)
    assert result.export_violation_kwh > 0
    assert result.prohibited_grid_charge_kwh == 0
    assert any(
        row.reserve_target_soc == 0.9 for row in result.ledger if row.start >= 1800
    )


def test_record_and_display_frequency_do_not_change_physics() -> None:
    scenario = cases()["pv_jump"]
    frequent = run_probe(
        scenario, physical_step=60, record_period=1, display_period=0.1
    )
    rare = run_probe(
        scenario, physical_step=60, record_period=3600, display_period=3600
    )
    assert frequent.decisions == rare.decisions
    assert frequent.ledger == rare.ledger
    assert _totals(frequent) == _totals(rare)


def test_control_period_is_a_strategy_change_not_an_integration_error() -> None:
    scenario = cases()["pv_jump"]
    hourly = run_probe(scenario, physical_step=60)
    half_hour = run_probe(scenario, physical_step=60, control_period=1800)
    assert [item.time for item in half_hour.decisions] == [0, 1800, 3600, 5400]
    assert half_hour.export_violation_kwh < hourly.export_violation_kwh
    assert _totals(half_hour) != _totals(hourly)


def test_invalid_fact_coverage_rejected_without_input_repair() -> None:
    scenario = cases()["pv_jump"]
    bad: Case = replace(
        scenario,
        segments=(replace(scenario.segments[0], end=1700), scenario.segments[1]),
    )
    with pytest.raises(ValueError, match="contiguous"):
        run_probe(bad, physical_step=60)
