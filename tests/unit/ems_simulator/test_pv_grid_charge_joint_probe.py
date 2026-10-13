"""Contract tests for the single-ledger PV/permission joint simulation."""

from dataclasses import fields
from itertools import pairwise

import pytest

from tools.dynamic_constraint_probe import HOUR_SECONDS, run_probe
from tools.pv_grid_charge_joint_probe import (
    ENERGY_TOL_KWH,
    POWER_TOL_KW,
    JointResult,
    run_joint,
    scenarios,
)


def _totals(result: JointResult) -> tuple[float, ...]:
    rows = result.execution.ledger
    return (
        result.execution.final_soc,
        *(
            sum(getattr(row, key) for row in rows)
            for key in (
                "available_pv_kwh",
                "delivered_pv_kwh",
                "curtailed_pv_kwh",
                "load_kwh",
                "battery_kwh",
                "import_kwh",
                "export_kwh",
                "grid_to_battery_kwh",
                "conversion_loss_kwh",
            )
        ),
    )


@pytest.mark.parametrize("name", tuple(scenarios()))
@pytest.mark.parametrize("mode", ("ideal", "dynamic"))
def test_joint_one_ledger_and_three_physical_steps(name: str, mode: str) -> None:
    results = [
        run_joint(scenarios()[name], mode=mode, physical_step_s=step)
        for step in (3600, 60, 15)
    ]
    for result in results:
        assert result.passed
        assert result.execution.settings.strict_startup_observation
        assert not result.execution.settings.current_pv_surplus_guard
        assert result.execution.settings.guard_controlled_pv_rise
        rows = result.execution.ledger
        assert rows[0].start_s == 0
        assert rows[-1].end_s == 7200
        assert len(result.execution.decisions) == 2
        assert tuple(decision.at for decision in result.execution.decisions) == (
            0,
            3600,
        )
        for previous, current in pairwise(rows):
            assert abs(previous.end_s - current.start_s) < 1e-7
        for row in rows:
            hours = (row.end_s - row.start_s) / HOUR_SECONDS
            assert hours > 0
            assert (
                abs(row.available_pv_kwh - row.delivered_pv_kwh - row.curtailed_pv_kwh)
                < ENERGY_TOL_KWH
            )
            assert (
                abs(
                    row.load_kw
                    + row.actual_battery_kw
                    - row.delivered_pv_kw
                    - row.grid_kw
                )
                < POWER_TOL_KW
            )
            assert (
                abs(
                    row.load_kwh
                    + row.battery_kwh
                    - row.delivered_pv_kwh
                    - row.import_kwh
                    + row.export_kwh
                )
                < ENERGY_TOL_KWH
            )
            assert (
                abs(row.storage_delta_kwh + row.conversion_loss_kwh - row.battery_kwh)
                < ENERGY_TOL_KWH
            )
            assert abs(row.battery_kwh - row.actual_battery_kw * hours) < ENERGY_TOL_KWH
            assert -3 - POWER_TOL_KW <= row.actual_battery_kw <= 3 + POWER_TOL_KW
            assert 0.2 - 1e-9 <= row.soc_after <= 1 + 1e-9
            assert row.import_kwh >= 0 and row.export_kwh >= 0
            assert (
                abs(
                    row.prohibited_grid_charge_kwh
                    - (row.grid_to_battery_kwh if not row.grid_charge_allowed else 0.0)
                )
                < ENERGY_TOL_KWH
            )
        if mode == "ideal":
            assert result.execution.export_peak_kw <= POWER_TOL_KW
            assert result.execution.export_kwh <= ENERGY_TOL_KWH
            assert result.execution.export_duration_s == 0
            assert not result.excursions
        else:
            assert all(excursion.within_budget for excursion in result.excursions)
            for excursion in result.excursions:
                if excursion.kind == "ZERO_EXPORT":
                    assert excursion.peak_kw <= 8 + POWER_TOL_KW
                    assert excursion.duration_s <= 95 + 1e-7
                    assert excursion.energy_kwh <= 8 * 95 / 3600 + ENERGY_TOL_KWH
                else:
                    assert excursion.peak_kw <= 3 + POWER_TOL_KW
                    assert excursion.duration_s <= 90 + 1e-7
                    assert excursion.energy_kwh <= 3 * 90 / 3600 + ENERGY_TOL_KWH
    for a, b in zip(_totals(results[0]), _totals(results[1]), strict=True):
        assert abs(a - b) <= ENERGY_TOL_KWH
    for a, b in zip(_totals(results[1]), _totals(results[2]), strict=True):
        assert abs(a - b) <= ENERGY_TOL_KWH


def test_revoke_then_pv_loss_records_the_delayed_surplus_response() -> None:
    result = run_joint(
        scenarios()["revoke_pv_loss"], mode="dynamic", physical_step_s=60
    )
    rows = result.execution.ledger
    assert any(row.original_request_kw > 0 and row.start_s >= 2000 for row in rows)
    assert any(
        row.prohibited_grid_charge_kwh > 0 for row in rows if 2000 <= row.start_s < 2050
    )
    assert all(
        row.prohibited_grid_charge_kwh <= ENERGY_TOL_KWH
        for row in rows
        if row.start_s >= 2050
    )
    assert any(
        event.source_at_s == 2000
        and event.actual_stop_at_s == 2050
        and abs(event.violation_energy_kwh - 2 * 50 / 3600) < ENERGY_TOL_KWH
        for event in result.event_outcomes
        if event.constraint == "GRID_CHARGE_FORBIDDEN"
    )
    assert any(row.grid_kw > 0 and not row.grid_charge_allowed for row in rows)
    assert any(f.code == "SOFT_RESERVE_UNMET" for f in result.findings)


def test_interleaved_permission_records_delay_but_does_not_replay_after_effect() -> (
    None
):
    case = scenarios()["interleaved_permission"]
    joint = run_joint(case, mode="dynamic", physical_step_s=60)
    assert any(
        1820 <= row.start_s < 1870
        and row.effective_permission
        and not row.grid_charge_allowed
        and row.prohibited_grid_charge_kwh > 0
        for row in joint.execution.ledger
    )
    assert any(
        1930 <= row.start_s < 3600
        and row.grid_charge_allowed
        and row.effective_permission
        and row.original_request_kw > 0
        and row.actual_battery_kw <= POWER_TOL_KW
        for row in joint.execution.ledger
    )
    assert any(
        event.source_at_s == 1820
        and event.actual_stop_at_s == 1870
        and event.violation_energy_kwh > 0
        for event in joint.event_outcomes
        if event.constraint == "GRID_CHARGE_FORBIDDEN"
    )


def test_active_charge_revoke_has_prebudgeted_lag_and_no_restore_replay() -> None:
    case = scenarios()["late_revoke"]
    joint = run_joint(case, mode="dynamic", physical_step_s=60)
    assert any(
        row.actual_battery_kw > 0
        for row in joint.execution.ledger
        if 3900 <= row.start_s < 4000
    )
    assert any(row.prohibited_grid_charge_kwh > 0 for row in joint.execution.ledger)
    assert any(
        event.source_at_s == 4000
        and event.actual_stop_at_s == 4030
        and abs(event.violation_energy_kwh - 0.025) < ENERGY_TOL_KWH
        for event in joint.event_outcomes
        if event.constraint == "GRID_CHARGE_FORBIDDEN"
    )
    assert all(
        row.actual_battery_kw <= POWER_TOL_KW
        for row in joint.execution.ledger
        if 4100 <= row.start_s < 7200
    )
    assert any(
        event.source_at_s == 4100
        and not event.had_violation
        and event.actual_stop_at_s is None
        for event in joint.event_outcomes
        if event.constraint == "ZERO_EXPORT"
    )


def test_permission_off_startup_cannot_use_not_yet_delivered_pv() -> None:
    result = run_joint(
        scenarios()["permission_off_pv_startup"], mode="dynamic", physical_step_s=60
    )
    assert result.execution.checks[0].check_at == 60
    assert result.execution.checks[0].effect_at == 70
    assert any(row.original_request_kw > 0 for row in result.execution.ledger)
    assert all(
        row.grid_to_battery_kwh <= ENERGY_TOL_KWH for row in result.execution.ledger
    )
    assert all(
        not event.had_violation and event.actual_stop_at_s is None
        for event in result.event_outcomes
        if event.constraint == "GRID_CHARGE_FORBIDDEN"
    )


def test_joint_pv_rise_and_permission_revoke_have_separate_transients() -> None:
    result = run_joint(
        scenarios()["revoke_pv_jump_ramp"], mode="dynamic", physical_step_s=60
    )
    assert any(
        event.source_at_s == 1800
        and event.had_violation
        and event.actual_stop_at_s == 1804
        and event.violation_energy_kwh > 0
        for event in result.event_outcomes
        if event.constraint == "GRID_CHARGE_FORBIDDEN"
    )
    assert all(
        row.prohibited_grid_charge_kwh <= ENERGY_TOL_KWH
        for row in result.execution.ledger
        if row.start_s >= 1870
    )
    assert any(item.kind == "ZERO_EXPORT" for item in result.excursions)


def test_pv_and_battery_are_coordinated_when_load_drops() -> None:
    case = scenarios()["discharge_load_drop"]
    ideal = run_joint(case, mode="ideal", physical_step_s=60)
    dynamic = run_joint(case, mode="dynamic", physical_step_s=60)
    assert ideal.execution.export_kwh == 0
    assert dynamic.execution.export_kwh > 0
    assert any(
        row.delivered_pv_kw > 0 and row.actual_battery_kw < 0
        for row in ideal.execution.ledger
        if row.load_kw > 1
    )
    assert all(
        row.grid_kw >= -POWER_TOL_KW
        for row in ideal.execution.ledger
        if row.zero_export_requested
    )


@pytest.mark.parametrize(
    "name,limit", (("upper_soc_same_time", 1.0), ("lower_soc_same_time", 0.2))
)
def test_soc_limit_and_scheduled_ems_same_time(name: str, limit: float) -> None:
    result = run_joint(scenarios()[name], mode="ideal", physical_step_s=3600)
    boundary = [row for row in result.execution.ledger if abs(row.end_s - 3600) < 1e-7]
    assert boundary
    assert abs(boundary[-1].soc_after - limit) < 1e-9
    assert len(result.execution.decisions) == 2
    assert abs(result.execution.decisions[1].feedback_soc - limit) < 1e-9


def test_full_battery_joint_curtailment_and_dynamic_excursions_are_not_erased() -> None:
    case = scenarios()["full_pv_load_drop"]
    ideal = run_joint(case, mode="ideal", physical_step_s=60)
    dynamic = run_joint(case, mode="dynamic", physical_step_s=60)
    assert ideal.execution.export_kwh == 0
    assert sum(row.curtailed_pv_kwh for row in ideal.execution.ledger) > 0
    assert len(dynamic.excursions) == 2
    assert all(
        item.kind == "ZERO_EXPORT" and item.within_budget for item in dynamic.excursions
    )
    assert dynamic.execution.export_kwh > 0
    assert (
        abs(
            dynamic.execution.export_kwh
            - sum(item.energy_kwh for item in dynamic.excursions)
        )
        < ENERGY_TOL_KWH
    )


def test_threshold_chatter_has_no_extra_dynamic_ems_or_event_checks() -> None:
    case = scenarios()["threshold_chatter"]
    result = run_joint(case, mode="dynamic", physical_step_s=15)
    assert tuple(decision.at for decision in result.execution.decisions) == (0, 3600)
    assert tuple(check.check_at for check in result.execution.checks) == tuple(
        range(60, 7200, 60)
    )
    assert result.execution.export_kwh == 0
    assert all(
        row.prohibited_grid_charge_kwh <= ENERGY_TOL_KWH
        for row in result.execution.ledger
    )


def test_record_cadence_is_not_a_decision_or_physics_clock() -> None:
    case = scenarios()["same_time_facts"]
    slow = run_joint(case, mode="dynamic", physical_step_s=60, record_period_s=3600)
    fast = run_joint(case, mode="dynamic", physical_step_s=60, record_period_s=15)
    assert slow.execution.decisions == fast.execution.decisions
    assert slow.execution.checks == fast.execution.checks
    assert slow.execution.ledger == fast.execution.ledger
    assert slow.findings == fast.findings


def test_joint_entry_keeps_one_execution_result_and_full_row_schema() -> None:
    result = run_joint(
        scenarios()["same_time_facts"], mode="dynamic", physical_step_s=60
    )
    names = {field.name for field in fields(result.execution.ledger[0])}
    assert {
        "original_request_kw",
        "constrained_request_kw",
        "actual_battery_kw",
        "available_pv_kwh",
        "delivered_pv_kwh",
        "curtailed_pv_kwh",
        "conversion_loss_kwh",
        "import_kwh",
        "export_kwh",
    } <= names
    assert result.execution.ledger[0].start_s == 0
    assert result.execution.ledger[-1].end_s == 7200
    assert sum(row.prohibited_grid_charge_kwh for row in result.execution.ledger) > 0


def test_old_full_battery_8_kwh_export_replays_in_the_joint_entry() -> None:
    case = scenarios()["full_battery_legacy"]
    old = run_probe(case, physical_step=60)
    ideal = run_joint(case, mode="ideal", physical_step_s=60)
    dynamic = run_joint(case, mode="dynamic", physical_step_s=60)
    assert abs(old.export_violation_kwh - 8.0) < ENERGY_TOL_KWH
    assert (
        abs(sum(row.available_pv_kwh for row in ideal.execution.ledger) - 10)
        < ENERGY_TOL_KWH
    )
    assert (
        abs(sum(row.delivered_pv_kwh for row in ideal.execution.ledger) - 2)
        < ENERGY_TOL_KWH
    )
    assert (
        abs(sum(row.curtailed_pv_kwh for row in ideal.execution.ledger) - 8)
        < ENERGY_TOL_KWH
    )
    assert ideal.execution.export_kwh == 0
    assert ideal.execution.final_soc == 1
    assert dynamic.execution.export_kwh == 0
    assert dynamic.execution.final_soc == 1
    assert (
        abs(
            sum(
                row.available_pv_kwh - row.delivered_pv_kwh - row.curtailed_pv_kwh
                for row in dynamic.execution.ledger
            )
        )
        < ENERGY_TOL_KWH
    )
