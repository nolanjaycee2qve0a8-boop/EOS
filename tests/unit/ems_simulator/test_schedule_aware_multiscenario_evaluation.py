"""Structural and observed-fixture validation for TASK-154 evaluation."""

import csv
from io import StringIO
from pathlib import Path

from ems_simulator.schedule_aware_multiscenario_evaluation import (
    run_evaluation,
    scenario_matrix,
)


def test_required_scenarios_are_stable_and_have_explicit_daily_facts() -> None:
    scenarios = scenario_matrix()

    assert tuple(scenario.scenario_id for scenario in scenarios) == (
        "S0",
        "S1",
        "S2",
        "S3",
        "S4",
        "S5",
        "S6",
        "S7",
    )
    assert all(
        len(scenario.pv_profile_kw)
        == len(scenario.load_profile_kw)
        == len(scenario.tariff_profile_cny_per_kwh)
        == 24
        for scenario in scenarios
    )
    assert all(scenario.expected_opportunity_count == 2 for scenario in scenarios)


def test_matrix_preserves_s0_regression_and_sensitivity_relationships(
    tmp_path: Path,
) -> None:
    result = run_evaluation(tmp_path)
    by_id = {item.scenario.scenario_id: item for item in result.scenario_results}

    assert all(
        len(item.execution.full_result.step_traces)
        == len(item.execution.rolling_result.step_traces)
        == len(item.execution.schedule_result.step_traces)
        == 24
        for item in result.scenario_results
    )
    assert by_id["S0"].schedule_early.adjusted_headroom_kwh == 8.0
    assert by_id["S0"].schedule_early.allowed_grid_charge_kw == 0.0
    assert by_id["S0"].control_classification == "FULL_LIKE"
    s1_depletion = by_id["S1"].schedule_early.stored_depletion_potential_kwh
    s2_depletion = by_id["S2"].schedule_early.stored_depletion_potential_kwh
    assert s1_depletion is not None
    assert s2_depletion is not None
    assert s1_depletion > s2_depletion
    s4_entries = (
        by_id["S4"]
        .execution.schedule_result.step_traces[0]
        .multi_opportunity_mpc_cycle_result.multi_opportunity_optimization_output.headroom_schedule.entries
    )
    s5_entries = (
        by_id["S5"]
        .execution.schedule_result.step_traces[0]
        .multi_opportunity_mpc_cycle_result.multi_opportunity_optimization_output.headroom_schedule.entries
    )
    assert len(s4_entries) == len(s5_entries) == 2
    assert (
        s4_entries[1].headroom_requirement.required_headroom_energy_kwh
        < s5_entries[1].headroom_requirement.required_headroom_energy_kwh
    )
    assert by_id["S7"].scenario.initial_soc > by_id["S6"].scenario.initial_soc
    assert by_id["S4"].control_classification == "INTERMEDIATE"


def test_evaluation_exports_deterministic_summary_scenario_csvs_and_svgs(
    tmp_path: Path,
) -> None:
    first = run_evaluation(tmp_path / "first")
    summary = first.scenario_summary_path.read_text(encoding="utf-8")
    report = first.evaluation_summary_path.read_text(encoding="utf-8")
    rows = tuple(csv.DictReader(StringIO(summary)))

    assert len(rows) == 8
    assert rows[0]["scenario_id"] == "S0"
    assert {
        "schedule_early_adjusted_headroom_kwh",
        "schedule_target_class",
        "schedule_allowance_class",
        "schedule_control_class",
    } <= set(rows[0])
    assert "not a statistical claim about household populations" in report
    assert all(
        path.exists()
        for path in (
            first.early_target_svg_path,
            first.early_allowance_svg_path,
            first.grid_import_svg_path,
            first.pv_absorption_svg_path,
        )
    )
    assert all(
        item.execution.comparison_csv_path.exists() for item in first.scenario_results
    )

    second = run_evaluation(tmp_path / "second")
    assert second.scenario_summary_path.read_text(encoding="utf-8") == summary
    assert second.evaluation_summary_path.read_text(encoding="utf-8") == report
    assert second.early_target_svg_path.read_text(encoding="utf-8") == (
        first.early_target_svg_path.read_text(encoding="utf-8")
    )
