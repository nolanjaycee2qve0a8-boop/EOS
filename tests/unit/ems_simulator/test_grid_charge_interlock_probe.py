"""Periodic permission-interlock timing and physical-ledger acceptance."""

from math import isclose

import pytest

from tools.dynamic_constraint_probe import DURATION_SECONDS
from tools.dynamic_constraint_probe import cases as predecessor_cases
from tools.dynamic_constraint_probe import run_probe as run_predecessor
from tools.grid_charge_interlock_probe import (
    InterlockResult,
    InterlockSettings,
    run_interlock,
    scenarios,
)

ENERGY_TOL = 8e-11
POWER_TOL = 1e-10
SOC_TOL = 1e-9
TIME_TOL = 1e-9


def _totals(result: InterlockResult) -> tuple[float, ...]:
    rows = result.ledger
    return (
        result.final_soc,
        sum(row.load_kwh for row in rows),
        sum(row.pv_kwh for row in rows),
        sum(row.battery_kwh for row in rows),
        sum(row.import_kwh for row in rows),
        sum(row.export_kwh for row in rows),
        sum(row.grid_to_battery_kwh for row in rows),
        sum(row.prohibited_grid_charge_kwh for row in rows),
        sum(row.conversion_loss_kwh for row in rows),
    )


@pytest.mark.parametrize("name", tuple(scenarios()))
def test_all_scenarios_conserve_and_match_three_physical_steps(name: str) -> None:
    case = scenarios()[name]
    results = [
        run_interlock(case, physical_step_s=step) for step in (3600.0, 60.0, 15.0)
    ]
    baseline = _totals(results[0])
    for result in results:
        assert [item.at for item in result.ems_decisions] == [0, 3600]
        assert len(result.execution_checks) == 120
        assert [item.check_at for item in result.execution_checks] == list(
            range(0, DURATION_SECONDS, 60)
        )
        assert result.ledger[0].start_s == 0
        assert result.ledger[-1].end_s == DURATION_SECONDS
        for prior, row in zip(result.ledger, result.ledger[1:], strict=False):
            assert abs(prior.end_s - row.start_s) <= TIME_TOL
        boundaries = {
            *(fact.start for fact in case.segments),
            *(fact.end for fact in case.segments),
            *(check.check_at for check in result.execution_checks),
            *(check.effect_at for check in result.execution_checks),
            3600,
        }
        for row in result.ledger:
            hours = (row.end_s - row.start_s) / 3600
            assert row.end_s > row.start_s
            assert 0.2 - SOC_TOL <= row.soc_after <= 1 + SOC_TOL
            assert abs(row.actual_battery_kw) <= 3 + POWER_TOL
            assert abs(row.constrained_request_kw) <= 3 + POWER_TOL
            assert (
                abs(row.grid_kw - (row.load_kw + row.actual_battery_kw - row.pv_kw))
                <= POWER_TOL
            )
            for boundary in boundaries:
                assert not (row.start_s < boundary < row.end_s)
            tolerance = 4e-11 * max(hours, 1 / 3600)
            assert (
                abs(
                    row.load_kwh
                    + row.battery_kwh
                    - row.pv_kwh
                    - row.import_kwh
                    + row.export_kwh
                )
                <= tolerance
            )
            expected_delta = (
                row.battery_kwh * 0.95
                if row.battery_kwh > 0
                else row.battery_kwh / 0.95
            )
            assert abs(row.storage_delta_kwh - expected_delta) <= tolerance
            assert (
                abs(row.conversion_loss_kwh - (row.battery_kwh - row.storage_delta_kwh))
                <= tolerance
            )
            assert row.conversion_loss_kwh >= -ENERGY_TOL
            expected_grid_charge_kw = max(
                0.0, row.actual_battery_kw - max(row.pv_kw - row.load_kw, 0.0)
            )
            assert (
                abs(row.grid_to_battery_kwh - expected_grid_charge_kw * hours)
                <= tolerance
            )
            assert row.grid_to_battery_kwh <= row.import_kwh + ENERGY_TOL
            assert (
                abs(
                    row.normal_load_import_kwh
                    + row.grid_to_battery_kwh
                    - row.import_kwh
                )
                <= tolerance
            )
            assert row.normal_load_import_kwh >= -ENERGY_TOL
            assert (
                abs(
                    row.pv_to_battery_kwh
                    + row.grid_to_battery_kwh
                    - max(row.battery_kwh, 0.0)
                )
                <= tolerance
            )
            assert row.prohibited_grid_charge_kwh == (
                row.grid_to_battery_kwh if not row.source_permission else 0.0
            )
            assert row.curtailed_pv_kwh == 0
        for index, (actual, expected) in enumerate(
            zip(_totals(result), baseline, strict=True)
        ):
            assert abs(actual - expected) <= (SOC_TOL if index == 0 else ENERGY_TOL)


def test_old_1_5_kwh_failure_is_retained_and_new_lag_is_prebudgeted() -> None:
    old = run_predecessor(predecessor_cases()["permission_mid_tick"], physical_step=60)
    assert old.prohibited_grid_charge_kwh == 1.5

    result = run_interlock(scenarios()["no_pv_revoke"], physical_step_s=60)
    assert result.ems_decisions[0].original_request_kw == 3
    assert result.revocations == (result.revocations[0],)
    outcome = result.revocations[0]
    assert outcome.source_revoke_at == 1800
    assert outcome.effective_off_at == 1870
    assert outcome.initial_grid_charge_stop_at == 1870
    assert outcome.initial_stop_delay_s == 70
    assert outcome.budget_s == 90
    assert outcome.budget_kwh == 0.075
    assert isclose(outcome.lag_violation_kwh, 3 * 70 / 3600, abs_tol=ENERGY_TOL)
    assert outcome.lag_violation_kwh <= outcome.budget_kwh + ENERGY_TOL
    assert outcome.post_gate_transient_kwh == 0
    assert outcome.steady_residual_kwh == 0
    assert all(
        row.grid_to_battery_kwh == 0
        for row in result.ledger
        if 1870 <= row.start_s < 3600
    )
    assert any(
        row.start_s == 1870
        and row.original_request_kw == 3
        and row.constrained_request_kw == 0
        and row.reason == "PV_ONLY_WHILE_REVOKED"
        for row in result.ledger
    )


def test_insufficient_pv_does_not_block_normal_grid_import_for_load() -> None:
    result = run_interlock(scenarios()["pv_insufficient"], physical_step_s=60)
    assert result.revocations[0].initial_stop_delay_s == 70
    assert result.revocations[0].steady_residual_kwh == 0
    assert any(
        row.start_s >= 1870
        and row.start_s < 3600
        and row.actual_battery_kw == 0
        and row.grid_kw == 1
        and row.normal_load_import_kwh > 0
        for row in result.ledger
    )


def test_pv_surplus_may_charge_battery_after_permission_off() -> None:
    result = run_interlock(scenarios()["pv_surplus"], physical_step_s=60)
    assert result.revocations[0].effective_off_at == 1870
    assert result.revocations[0].initial_stop_delay_s == 0
    assert result.revocations[0].lag_violation_kwh == 0
    assert any(
        row.start_s >= 1870
        and row.start_s < 3600
        and row.constrained_request_kw == 2
        and row.actual_battery_kw == 2
        and row.pv_to_battery_kwh > 0
        and row.grid_to_battery_kwh == 0
        for row in result.ledger
    )


def test_ordinary_grid_import_is_allowed_while_grid_charge_is_forbidden() -> None:
    result = run_interlock(scenarios()["normal_load_import"], physical_step_s=60)
    assert result.revocations == ()
    assert sum(row.import_kwh for row in result.ledger) == 4
    assert all(row.grid_to_battery_kwh == 0 for row in result.ledger)
    assert all(row.actual_battery_kw == 0 for row in result.ledger)


def test_pv_loss_under_revoked_permission_has_its_own_response_budget() -> None:
    result = run_interlock(scenarios()["pv_loss_while_revoked"], physical_step_s=60)
    revoke = result.revocations[0]
    assert revoke.effective_off_at == 1870
    assert revoke.initial_stop_delay_s == 0
    assert revoke.lag_violation_kwh == 0
    assert isclose(revoke.post_gate_transient_kwh, 2 * 50 / 3600, abs_tol=ENERGY_TOL)
    assert revoke.steady_residual_kwh == 0
    assert len(result.surplus_losses) == 1
    loss = result.surplus_losses[0]
    assert loss.source_change_at == 2000
    assert loss.observed_effect_at == 2050
    assert loss.actual_grid_charge_stop_at == 2050
    assert loss.stop_delay_s == 50
    assert loss.budget_s == 90
    assert isclose(loss.transient_violation_kwh, 2 * 50 / 3600, abs_tol=ENERGY_TOL)
    assert loss.transient_violation_kwh <= loss.budget_kwh + ENERGY_TOL
    assert loss.steady_residual_kwh == 0
    assert any(
        row.start_s == 2000
        and row.effective_permission is False
        and row.constrained_request_kw == 2
        and row.grid_to_battery_kwh > 0
        for row in result.ledger
    )
    assert all(
        row.grid_to_battery_kwh == 0
        for row in result.ledger
        if 2050 <= row.start_s < 3600
    )


def test_unrelated_policy_boundary_cannot_truncate_pv_loss_accounting() -> None:
    result = run_interlock(scenarios()["pv_loss_policy_marker"], physical_step_s=60)
    loss = result.surplus_losses[0]
    assert len(result.surplus_losses) == 1
    assert loss.source_change_at == 2000
    assert loss.observed_effect_at == 2050
    assert loss.actual_grid_charge_stop_at == 2050
    assert loss.stop_delay_s == 50
    assert isclose(loss.transient_violation_kwh, 2 * 50 / 3600, abs_tol=ENERGY_TOL)
    assert loss.steady_residual_kwh == 0
    assert isclose(
        result.revocations[0].post_gate_transient_kwh,
        loss.transient_violation_kwh,
        abs_tol=ENERGY_TOL,
    )


def test_equal_net_surplus_fact_boundary_cannot_truncate_loss_accounting() -> None:
    result = run_interlock(
        scenarios()["pv_loss_same_surplus_marker"], physical_step_s=60
    )
    assert len(result.surplus_losses) == 1
    loss = result.surplus_losses[0]
    assert loss.source_change_at == 2000
    assert loss.observed_effect_at == 2050
    assert loss.actual_grid_charge_stop_at == 2050
    assert loss.stop_delay_s == 50
    assert isclose(loss.transient_violation_kwh, 50 / 3600, abs_tol=ENERGY_TOL)
    assert loss.steady_residual_kwh == 0
    assert isclose(
        result.revocations[0].post_gate_transient_kwh,
        loss.transient_violation_kwh,
        abs_tol=ENERGY_TOL,
    )


def test_second_surplus_loss_exactly_on_first_effect_is_separate() -> None:
    result = run_interlock(scenarios()["pv_loss_on_prior_effect"], physical_step_s=60)
    first, second = result.surplus_losses
    assert first.source_change_at == 2000
    assert first.observed_effect_at == 2050
    assert first.stop_delay_s == 50
    assert isclose(first.transient_violation_kwh, 50 / 3600, abs_tol=ENERGY_TOL)
    assert first.steady_residual_kwh == 0
    assert second.source_change_at == 2050
    assert second.observed_effect_at == 2110
    assert second.stop_delay_s == 60
    assert isclose(second.transient_violation_kwh, 60 / 3600, abs_tol=ENERGY_TOL)
    assert second.steady_residual_kwh == 0
    assert isclose(
        result.revocations[0].post_gate_transient_kwh,
        110 / 3600,
        abs_tol=ENERGY_TOL,
    )


def test_terminal_revoke_is_censored_not_reported_as_stopped() -> None:
    result = run_interlock(scenarios()["late_revoke"], physical_step_s=60)
    outcome = result.revocations[0]
    assert outcome.source_revoke_at == 7190
    assert outcome.effective_off_at is None
    assert outcome.initial_grid_charge_stop_at is None
    assert outcome.initial_stop_delay_s is None
    assert outcome.steady_residual_kwh is None
    assert isclose(outcome.lag_violation_kwh, 3 * 10 / 3600, abs_tol=ENERGY_TOL)
    assert any(
        row.start_s == 7190
        and row.effective_permission is True
        and row.grid_to_battery_kwh > 0
        for row in result.ledger
    )


def test_terminal_pv_loss_is_censored_not_reported_as_stopped() -> None:
    result = run_interlock(scenarios()["late_pv_loss"], physical_step_s=60)
    loss = result.surplus_losses[0]
    assert loss.source_change_at == 7190
    assert loss.observed_effect_at is None
    assert loss.actual_grid_charge_stop_at is None
    assert loss.stop_delay_s is None
    assert loss.steady_residual_kwh is None
    assert isclose(loss.transient_violation_kwh, 2 * 10 / 3600, abs_tol=ENERGY_TOL)
    assert result.revocations[0].steady_residual_kwh is None
    assert any(
        row.start_s == 7190
        and row.effective_permission is False
        and row.grid_to_battery_kwh > 0
        for row in result.ledger
    )


def test_restore_does_not_replay_stale_ems_request() -> None:
    result = run_interlock(scenarios()["revoke_restore"], physical_step_s=60)
    assert [
        (item.effective_at, item.permission) for item in result.gate_transitions
    ] == [
        (1870, False),
        (3070, True),
    ]
    assert all(
        row.original_request_kw == 3
        and row.constrained_request_kw == 0
        and row.reason == "RESTORED_AWAIT_FRESH_EMS"
        for row in result.ledger
        if 3070 <= row.start_s < 3600
    )
    assert result.ems_decisions[1].at == 3600
    assert result.ems_decisions[1].original_request_kw == 3
    assert any(
        row.start_s == 3600 and row.constrained_request_kw == 3 for row in result.ledger
    )


def test_repeated_revoke_is_one_gate_transition() -> None:
    result = run_interlock(scenarios()["repeat_revoke"], physical_step_s=60)
    assert [
        (item.effective_at, item.permission) for item in result.gate_transitions
    ] == [(1870, False)]
    assert len(result.revocations) == 1
    assert any(row.end_s == 2400 for row in result.ledger)
    assert any(row.start_s == 2400 for row in result.ledger)
    assert result.revocations[0].steady_residual_kwh == 0


def test_revoke_on_execution_check_boundary_respects_actuation_delay() -> None:
    settings = InterlockSettings(60, 0, 10)
    result = run_interlock(
        scenarios()["check_boundary"], physical_step_s=3600, settings=settings
    )
    at_event = next(item for item in result.execution_checks if item.check_at == 1800)
    assert at_event.sampled_at == 1800
    assert at_event.observed_permission is False
    assert result.gate_transitions[0].effective_at == 1810
    assert result.revocations[0].initial_stop_delay_s == 10
    assert isclose(
        result.revocations[0].lag_violation_kwh,
        3 * 10 / 3600,
        abs_tol=ENERGY_TOL,
    )
    assert all(
        row.constrained_request_kw == 3
        for row in result.ledger
        if 1800 <= row.start_s < 1810
    )


def test_soc_boundary_still_limits_physical_delivery() -> None:
    result = run_interlock(scenarios()["soc_upper_boundary"], physical_step_s=3600)
    assert any(0 < row.end_s < 1800 and row.soc_after == 1 for row in result.ledger)
    assert all(row.soc_after <= 1 + SOC_TOL for row in result.ledger)
    assert result.revocations[0].initial_stop_delay_s == 0
    assert result.revocations[0].lag_violation_kwh == 0


def test_simultaneous_event_does_not_make_zero_export_pass() -> None:
    result = run_interlock(scenarios()["simultaneous"], physical_step_s=3600)
    assert [item.at for item in result.ems_decisions] == [0, 3600]
    assert [item.effective_at for item in result.gate_transitions] == [1870]
    assert all(not (row.start_s < 1800 < row.end_s) for row in result.ledger)
    assert any(row.start_s == 1800 for row in result.ledger)
    assert sum(row.export_kwh for row in result.ledger) > 0
    assert all(row.curtailed_pv_kwh == 0 for row in result.ledger)
    assert result.revocations[0].lag_violation_kwh == 0


def test_record_display_cadence_is_not_a_control_or_execution_clock() -> None:
    case = scenarios()["no_pv_revoke"]
    frequent = run_interlock(
        case, physical_step_s=60, record_period_s=1, display_period_s=0.1
    )
    rare = run_interlock(
        case, physical_step_s=60, record_period_s=3600, display_period_s=3600
    )
    assert frequent.ems_decisions == rare.ems_decisions
    assert frequent.execution_checks == rare.execution_checks
    assert frequent.gate_transitions == rare.gate_transitions
    assert frequent.ledger == rare.ledger
    assert frequent.revocations == rare.revocations


def test_execution_observation_delay_is_configurable_not_instantaneous() -> None:
    case = scenarios()["no_pv_revoke"]
    default = run_interlock(case, physical_step_s=60)
    instant_observation = run_interlock(
        case,
        physical_step_s=60,
        settings=InterlockSettings(60, 0, 10),
    )
    assert default.revocations[0].initial_stop_delay_s == 70
    assert instant_observation.revocations[0].initial_stop_delay_s == 10
    assert instant_observation.revocations[0].lag_violation_kwh < (
        default.revocations[0].lag_violation_kwh
    )


@pytest.mark.parametrize(
    "arguments",
    [(0, 20, 10), (61, 20, 10), (60, -1, 10), (60, 20, -1)],
)
def test_invalid_execution_cadence_or_delay_is_rejected(
    arguments: tuple[int, int, int],
) -> None:
    with pytest.raises(ValueError):
        InterlockSettings(*arguments)
