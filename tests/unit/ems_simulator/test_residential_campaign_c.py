"""Focused contract tests for frozen Residential EMS Campaign C tooling."""

from collections import Counter
from math import isclose
from pathlib import Path

from ems_simulator.residential_acceptance import NUMERIC_TOLERANCE
from ems_simulator.residential_campaign_c import (
    _shift_earlier,
    _shift_later,
    _svg_bar_chart,
    campaign_c_scenarios,
    run_residential_campaign_c,
)


def test_campaign_c_defines_exact_39_scenarios_and_separate_forecast_facts() -> None:
    scenarios = campaign_c_scenarios()

    assert len(scenarios) == 39
    assert len({scenario.scenario_id for scenario in scenarios}) == 39
    assert Counter(scenario.environment for scenario in scenarios) == {
        "REFERENCE": 13,
        "HIGH_EVENING_LOAD": 13,
        "HIGH_PV": 13,
    }
    assert Counter(scenario.forecast_error_case_id for scenario in scenarios) == {
        case: 3
        for case in (
            "PERFECT",
            "PV_OVER_25",
            "PV_UNDER_25",
            "LOAD_OVER_25",
            "LOAD_UNDER_25",
            "PV_EARLY_2H",
            "PV_LATE_2H",
            "LOAD_EARLY_2H",
            "LOAD_LATE_2H",
            "TARIFF_EARLY_2H",
            "TARIFF_LATE_2H",
            "OPTIMISTIC_COMBINED",
            "PESSIMISTIC_COMBINED",
        )
    }
    perfect = next(
        item for item in scenarios if item.scenario_id == "C_REFERENCE_PERFECT"
    )
    assert perfect.forecast_pv_profile_kw is perfect.realized_pv_profile_kw
    assert perfect.forecast_load_profile_kw is perfect.realized_load_profile_kw
    assert (
        perfect.forecast_tariff_profile_cny_per_kwh
        is perfect.realized_tariff_profile_cny_per_kwh
    )


def test_campaign_c_transformations_are_pure_and_timing_direction_is_explicit() -> None:
    profile = tuple(float(value) for value in range(24))

    assert _shift_earlier(profile, 2)[:4] == (2.0, 3.0, 4.0, 5.0)
    assert _shift_earlier(profile, 2)[-2:] == (0.0, 1.0)
    assert _shift_later(profile, 2)[:4] == (22.0, 23.0, 0.0, 1.0)
    assert len(_shift_earlier(profile, 2)) == 24
    assert sum(_shift_later(profile, 2)) == sum(profile)
    assert profile == tuple(float(value) for value in range(24))


def test_campaign_c_execution_uses_separate_forecast_and_realized_facts(
    tmp_path: Path,
) -> None:
    campaign = run_residential_campaign_c(tmp_path)
    assert len(campaign.scenario_results) == 39
    paths = tuple(
        path
        for result in campaign.scenario_results
        for path in (result.schedule, result.economic)
    )
    assert len(paths) == 78
    assert len({id(path.trajectory) for path in paths}) == 78
    assert all(len(path.trajectory.step_traces) == 24 for path in paths)
    assert all(
        len({id(trace) for trace in path.trajectory.step_traces}) == 24
        for path in paths
    )
    assert campaign.hard_passed
    assert campaign.perfect_anchor_reproduced

    forecast_case = next(
        result
        for result in campaign.scenario_results
        if result.scenario.scenario_id == "C_REFERENCE_PV_OVER_25"
    )
    trace = forecast_case.schedule.trajectory.step_traces[12]
    scenario = forecast_case.scenario
    assert (
        trace.forecast_horizon.points[0].pv_power_kw
        == scenario.forecast_pv_profile_kw[12]
    )
    assert (
        trace.simulation_trace.state.pv_result.actual_power_kw
        == scenario.realized_pv_profile_kw[12]
    )
    assert (
        trace.simulation_trace.state.load_result.actual_power_kw
        == scenario.realized_load_profile_kw[12]
    )
    assert (
        trace.simulation_trace.state.tariff_result.import_price_cny_per_kwh
        == scenario.realized_tariff_profile_cny_per_kwh[12]
    )
    economic_trace = forecast_case.economic.trajectory.step_traces[12]
    assert (
        economic_trace.forecast_horizon.points[0].pv_power_kw
        == scenario.forecast_pv_profile_kw[12]
    )

    perfect = next(
        result
        for result in campaign.scenario_results
        if result.scenario.scenario_id == "C_REFERENCE_PERFECT"
    )
    assert perfect.forecast_error.pv_signed_daily_energy_bias_kwh == 0.0
    assert perfect.forecast_error.load_mean_absolute_error_kw == 0.0
    assert perfect.forecast_error.tariff_maximum_absolute_error_cny_per_kwh == 0.0
    assert isclose(perfect.schedule.kpi.grid_import_energy_kwh, 13.122438, abs_tol=1e-6)
    assert isclose(perfect.schedule.kpi.final_soc_fraction, 0.2, abs_tol=1e-12)
    assert all(path.kpi.ledger_reconciled for path in paths)
    assert all(path.kpi.comparison_reconciled for path in paths)
    assert all(path.kpi.provenance_complete for path in paths)
    assert all(path.acceptance.passed for path in paths)

    regrets = {
        (
            item.path.scenario.scenario_id,
            item.path.strategy,
        ): item
        for item in campaign.anchor_regrets
    }
    anchor = regrets[("C_REFERENCE_PERFECT", "Schedule")]
    assert anchor.perfect_anchor_scenario_id == "C_REFERENCE_PERFECT"
    assert anchor.adjusted_cost_regret == 0.0
    assert anchor.actual_executed_battery_power_divergence_count == 0
    assert anchor.maximum_absolute_actual_executed_battery_power_difference_kw == 0.0
    load_timing_regret = regrets[("C_REFERENCE_LOAD_LATE_2H", "Schedule")]
    load_timing = next(
        result
        for result in campaign.scenario_results
        if result.scenario.scenario_id == "C_REFERENCE_LOAD_LATE_2H"
    )
    load_timing_actual_powers = tuple(
        trace.simulation_trace.state.battery_result.actual_power_kw
        for trace in load_timing.schedule.trajectory.step_traces
    )
    perfect_actual_powers = tuple(
        trace.simulation_trace.state.battery_result.actual_power_kw
        for trace in perfect.schedule.trajectory.step_traces
    )
    actual_power_differences = tuple(
        abs(imperfect_power - perfect_power)
        for imperfect_power, perfect_power in zip(
            load_timing_actual_powers,
            perfect_actual_powers,
            strict=True,
        )
    )
    independently_calculated_divergence_count = sum(
        difference > NUMERIC_TOLERANCE for difference in actual_power_differences
    )
    independently_calculated_maximum_difference = max(actual_power_differences)

    assert independently_calculated_divergence_count == 10
    assert isclose(
        independently_calculated_maximum_difference,
        1.6,
        abs_tol=NUMERIC_TOLERANCE,
    )
    assert (
        load_timing_regret.actual_executed_battery_power_divergence_count
        == independently_calculated_divergence_count
    )
    assert isclose(
        load_timing_regret.maximum_absolute_actual_executed_battery_power_difference_kw,
        independently_calculated_maximum_difference,
        abs_tol=NUMERIC_TOLERANCE,
    )
    assert any(
        trace.journal_record.final_action.action == "discharge"
        and trace.journal_record.final_requested_power_kw > 0.0
        and trace.simulation_trace.state.battery_result.actual_power_kw < 0.0
        for trace in load_timing.schedule.trajectory.step_traces
    )


def test_campaign_c_outputs_are_deterministic_and_svg_reporting_is_traceable(
    tmp_path: Path,
) -> None:
    first = run_residential_campaign_c(tmp_path / "first")
    second = run_residential_campaign_c(tmp_path / "second")
    first_files = {path.name: path for path in first.output_paths}
    second_files = {path.name: path for path in second.output_paths}

    assert first_files.keys() == second_files.keys()
    for name in first_files:
        assert first_files[name].read_text(encoding="utf-8") == second_files[
            name
        ].read_text(encoding="utf-8")
    assert {
        "campaign_c_scenarios.csv",
        "campaign_c_results.csv",
        "campaign_c_forecast_errors.csv",
        "campaign_c_anchor_regret.csv",
        "campaign_c_comparisons.csv",
        "campaign_c_findings.csv",
        "campaign_c_summary.txt",
        "forecast_pv_mae_kw.svg",
        "adjusted_cost_regret_cny.svg",
        "executed_battery_power_divergence.svg",
        "final_soc_delta.svg",
        "physical_revision_delta.svg",
        "schedule_economic_adjusted_cost_delta_cny.svg",
    }.issubset(first_files)
    svg = first_files["adjusted_cost_regret_cny.svg"].read_text(encoding="utf-8")
    assert 'id="zero-axis"' in svg
    assert "C_REFERENCE_PV_OVER_25 | REFERENCE | PV_OVER_25 | Schedule" in svg
    assert "unit=CNY" in svg
    assert "imperfect minus perfect" in svg


def test_campaign_c_svg_escapes_text_and_uses_computed_zero_axis() -> None:
    svg = _svg_bar_chart(
        "<title>", "kW", (('a<&"', -1.0), ("b", 1.0)), "<legend>", "#000"
    )

    assert 'id="zero-axis" x1="40" y1="155.00" x2="990" y2="155.00"' in svg
    assert "&lt;title&gt;" in svg
    assert 'data-label="a&lt;&amp;&quot;"' in svg
    assert "&lt;legend&gt;" in svg
