"""AC-bus PV curtailment and dynamic Zero Export acceptance."""

from itertools import pairwise
from math import isclose

import pytest

from tools.dynamic_constraint_probe import cases as predecessor_cases
from tools.dynamic_constraint_probe import run_probe
from tools.grid_charge_interlock_probe import run_interlock
from tools.grid_charge_interlock_probe import scenarios as interlock_scenarios
from tools.pv_curtailment_probe import (
    CurtailmentResult,
    CurtailmentSettings,
    run_curtailment,
    scenarios,
)

POWER_TOL_KW = 1e-9
ENERGY_TOL_KWH = 2e-9
SOC_TOL = 1e-9
TIME_TOL_S = 1e-7
STORAGE_TOL_KWH = 2e-9


def _totals(result: CurtailmentResult) -> tuple[float, ...]:
    rows = result.ledger
    return (
        result.final_soc,
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
                "prohibited_grid_charge_kwh",
                "conversion_loss_kwh",
            )
        ),
    )


def _export_excursions(
    result: CurtailmentResult,
) -> tuple[tuple[float, float, float], ...]:
    excursions: list[tuple[float, float, float]] = []
    for row in result.ledger:
        if not row.zero_export_requested or row.grid_kw >= -POWER_TOL_KW:
            continue
        if excursions and abs(excursions[-1][1] - row.start_s) <= TIME_TOL_S:
            start, _, energy = excursions[-1]
            excursions[-1] = (start, row.end_s, energy + row.export_kwh)
        else:
            excursions.append((row.start_s, row.end_s, row.export_kwh))
    return tuple(excursions)


@pytest.mark.parametrize("name", tuple(scenarios()))
@pytest.mark.parametrize("mode", ("ideal", "dynamic"))
def test_conservation_and_three_physical_steps(name: str, mode: str) -> None:
    settings = CurtailmentSettings.ideal() if mode == "ideal" else CurtailmentSettings()
    results = [
        run_curtailment(scenarios()[name], physical_step_s=step, settings=settings)
        for step in (3600.0, 60.0, 15.0)
    ]
    baseline = _totals(results[0])
    for result in results:
        assert [decision.at for decision in result.decisions] == [0, 3600]
        assert result.ledger[0].start_s == 0
        assert result.ledger[-1].end_s == 7200
        for prior, row in zip(result.ledger, result.ledger[1:], strict=False):
            assert abs(prior.end_s - row.start_s) <= TIME_TOL_S
        for row in result.ledger:
            assert row.end_s > row.start_s
            assert 0.2 - SOC_TOL <= row.soc_after <= 1 + SOC_TOL
            assert abs(row.actual_battery_kw) <= 3 + POWER_TOL_KW
            assert abs(row.constrained_request_kw) <= 3 + POWER_TOL_KW
            assert 0 <= row.delivered_pv_kw <= row.available_pv_kw + POWER_TOL_KW
            assert 0 <= row.pv_cap_kw <= settings.pv_ac_max_kw + POWER_TOL_KW
            assert (
                abs(row.available_pv_kwh - row.delivered_pv_kwh - row.curtailed_pv_kwh)
                <= ENERGY_TOL_KWH
            )
            assert (
                abs(
                    row.grid_kw
                    - (row.load_kw + row.actual_battery_kw - row.delivered_pv_kw)
                )
                <= POWER_TOL_KW
            )
            assert (
                abs(
                    row.load_kwh
                    + row.battery_kwh
                    - row.delivered_pv_kwh
                    - row.import_kwh
                    + row.export_kwh
                )
                <= ENERGY_TOL_KWH
            )
            assert (
                abs(row.battery_kwh - row.storage_delta_kwh - row.conversion_loss_kwh)
                <= ENERGY_TOL_KWH
            )
            expected_storage = row.battery_kwh * (
                0.95 if row.battery_kwh >= 0 else 1 / 0.95
            )
            assert abs(row.storage_delta_kwh - expected_storage) <= STORAGE_TOL_KWH
            assert row.prohibited_grid_charge_kwh == (
                row.grid_to_battery_kwh if not row.grid_charge_allowed else 0
            )
        for index, (actual, expected) in enumerate(
            zip(_totals(result), baseline, strict=True)
        ):
            assert abs(actual - expected) <= (SOC_TOL if index == 0 else ENERGY_TOL_KWH)
        if mode == "ideal":
            assert result.export_peak_kw <= POWER_TOL_KW
            assert result.export_kwh <= ENERGY_TOL_KWH
            assert result.export_duration_s == 0
        else:
            assert (
                result.export_peak_kw <= settings.export_peak_budget_kw + POWER_TOL_KW
            )
            for start, end, energy in _export_excursions(result):
                assert end - start <= settings.response_budget_s + TIME_TOL_S
                assert energy <= settings.export_energy_budget_kwh + ENERGY_TOL_KWH


def test_full_battery_old_8_kwh_export_is_real_then_ideally_curtailed() -> None:
    old = run_probe(predecessor_cases()["full_battery"], physical_step=60)
    assert old.export_violation_kwh == 8
    result = run_curtailment(
        scenarios()["full_battery"],
        physical_step_s=60,
        settings=CurtailmentSettings.ideal(),
    )
    rows = result.ledger
    assert isclose(
        sum(row.available_pv_kwh for row in rows), 10, abs_tol=ENERGY_TOL_KWH
    )
    assert isclose(sum(row.delivered_pv_kwh for row in rows), 2, abs_tol=ENERGY_TOL_KWH)
    assert isclose(sum(row.curtailed_pv_kwh for row in rows), 8, abs_tol=ENERGY_TOL_KWH)
    assert sum(row.battery_kwh for row in rows) == 0
    assert sum(row.import_kwh for row in rows) == 0
    assert sum(row.export_kwh for row in rows) == 0
    assert result.final_soc == 1


def test_delayed_full_battery_case_starts_fail_closed_without_a_measurement() -> None:
    result = run_curtailment(scenarios()["full_battery"], physical_step_s=60)
    assert result.checks[0].effect_at == 10
    startup = [row for row in result.ledger if row.start_s < 10]
    assert startup
    assert all(row.pv_cap_kw == 0 for row in startup)
    assert all(row.delivered_pv_kw == 0 for row in startup)
    assert all(row.actual_battery_kw == 0 for row in startup)
    assert isclose(
        sum(row.import_kwh for row in startup), 10 / 3600, abs_tol=ENERGY_TOL_KWH
    )
    assert result.export_peak_kw == 0
    assert result.export_duration_s == 0
    assert result.export_kwh == 0
    assert sum(row.curtailed_pv_kwh for row in result.ledger) > 0


def test_full_battery_pv_jump_waits_for_observation_then_slews() -> None:
    case = scenarios()["full_pv_jump"]
    ideal = run_curtailment(
        case, physical_step_s=60, settings=CurtailmentSettings.ideal()
    )
    dynamic = run_curtailment(case, physical_step_s=60)
    assert ideal.export_kwh == 0
    assert dynamic.export_peak_kw > 0
    assert dynamic.export_kwh > 0
    assert any(1800 <= row.start_s < 1870 and row.grid_kw < 0 for row in dynamic.ledger)
    assert any(
        row.start_s >= 1870 and row.curtailed_pv_kw > 0 for row in dynamic.ledger
    )
    assert all(
        row.export_kwh <= ENERGY_TOL_KWH
        for row in dynamic.ledger
        if 1875 <= row.start_s < 3600
    )


def test_ac_pv_output_ramp_is_a_real_one_second_limit() -> None:
    result = run_curtailment(scenarios()["full_pv_jump"], physical_step_s=15)
    affected = [row for row in result.ledger if 1800 <= row.start_s <= 1806]
    assert affected[0].start_s == 1800
    assert affected[0].delivered_pv_kw == 0
    assert [row.delivered_pv_kw for row in affected[:6]] == [0, 1, 2, 3, 4, 5]
    for before, after in pairwise(affected):
        positive_change = max(after.delivered_pv_kw - before.delivered_pv_kw, 0)
        assert positive_change <= (
            result.settings.pv_ramp_kw_per_s * (after.start_s - before.start_s)
            + POWER_TOL_KW
        )


def test_battery_only_discharge_is_coordinated_after_observation() -> None:
    ideal = run_curtailment(
        scenarios()["battery_only_export"],
        physical_step_s=60,
        settings=CurtailmentSettings.ideal(),
    )
    dynamic = run_curtailment(scenarios()["battery_only_export"], physical_step_s=60)
    assert ideal.export_kwh == 0
    assert any(
        row.start_s >= 1800 and row.constrained_request_kw == 0 for row in ideal.ledger
    )
    assert dynamic.export_kwh > 0
    assert any(
        row.start_s >= 1870 and row.constrained_request_kw == 0
        for row in dynamic.ledger
    )


def test_pv_and_battery_can_simultaneously_serve_the_same_ac_load() -> None:
    result = run_curtailment(
        scenarios()["pv_and_battery"],
        physical_step_s=60,
        settings=CurtailmentSettings.ideal(),
    )
    assert any(
        row.start_s >= 1800
        and row.delivered_pv_kw == 1
        and row.actual_battery_kw == -2
        and row.load_kw == 3
        and row.grid_kw == 0
        for row in result.ledger
    )


def test_permission_and_reserve_coexist_without_steady_grid_charge() -> None:
    result = run_curtailment(scenarios()["permission_reserve"], physical_step_s=60)
    assert result.decisions[0].original_request_kw == 3
    assert any(
        row.start_s >= 1870 and row.start_s < 3600 and row.original_request_kw == 3
        for row in result.ledger
    )
    assert all(
        row.grid_to_battery_kwh <= ENERGY_TOL_KWH
        for row in result.ledger
        if 1870 <= row.start_s < 3600
    )
    assert result.export_kwh <= result.settings.export_energy_budget_kwh
    predecessor = run_interlock(
        interlock_scenarios()["no_pv_revoke"], physical_step_s=60
    )
    assert predecessor.revocations[0].effective_off_at == 1870
    assert predecessor.revocations[0].steady_residual_kwh == 0


def test_record_and_display_cadence_do_not_change_physics_or_decisions() -> None:
    case = scenarios()["load_drop"]
    baseline = run_curtailment(
        case, physical_step_s=15, record_period_s=60, display_period_s=5
    )
    changed = run_curtailment(
        case, physical_step_s=15, record_period_s=900, display_period_s=0.25
    )
    assert _totals(changed) == _totals(baseline)
    assert changed.decisions == baseline.decisions
    assert changed.checks == baseline.checks


def test_control_cadence_change_is_not_mislabeled_integration_error() -> None:
    case = scenarios()["permission_reserve"]
    hourly = run_curtailment(case, physical_step_s=60, control_period_s=3600)
    half_hourly = run_curtailment(case, physical_step_s=60, control_period_s=1800)
    assert [decision.at for decision in half_hourly.decisions] == [0, 1800, 3600, 5400]
    assert len(hourly.decisions) == 2
    assert half_hourly.decisions != hourly.decisions


def test_simultaneous_facts_keep_source_event_and_effect_time_distinct() -> None:
    case = scenarios()["simultaneous"]
    result = run_curtailment(case, physical_step_s=60)
    assert [decision.at for decision in result.decisions] == [0, 3600]
    assert any(
        check.sampled_at >= 1800 and check.effect_at >= 1870 for check in result.checks
    )
    assert any(
        row.start_s == 1800
        and row.zero_export_requested
        and not row.effective_zero_export
        for row in result.ledger
    )
    assert any(
        row.start_s >= 1870 and row.effective_zero_export for row in result.ledger
    )


def test_settings_reject_invalid_simulation_assumptions() -> None:
    with pytest.raises(ValueError):
        CurtailmentSettings(check_period_s=0)
    with pytest.raises(ValueError):
        CurtailmentSettings(observation_delay_s=-1)
    with pytest.raises(ValueError):
        CurtailmentSettings(pv_ramp_kw_per_s=-1)
