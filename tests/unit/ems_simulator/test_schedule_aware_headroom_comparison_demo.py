"""Behavioral validation for TASK-153's three-path comparison read model."""

import csv
from io import StringIO
from pathlib import Path

from ems_simulator.schedule_aware_headroom_comparison_demo import run_demo


def test_comparison_runs_three_complete_paths_from_shared_finite_facts(
    tmp_path: Path,
) -> None:
    execution = run_demo(tmp_path)

    assert len(execution.full_result.step_traces) == 24
    assert len(execution.rolling_result.step_traces) == 24
    assert len(execution.schedule_result.step_traces) == 24
    assert (
        execution.full_source_input.integration_input
        is execution.rolling_source_input.integration_input
    )
    assert (
        execution.full_source_input.forecast_horizons
        is execution.rolling_source_input.forecast_horizons
    )
    assert (
        execution.full_source_input.forecast_horizons
        is execution.schedule_source_input.daily_mpc_input.forecast_horizons
    )


def test_comparison_reads_exact_outer_path_provenance(tmp_path: Path) -> None:
    execution = run_demo(tmp_path)
    full_trace = execution.full_result.step_traces[0]
    rolling_trace = execution.rolling_result.step_traces[0]
    schedule_trace = execution.schedule_result.step_traces[0]

    full_output = full_trace.headroom_mpc_cycle_result.headroom_optimization_output
    rolling_cycle = rolling_trace.rolling_headroom_mpc_cycle_result
    schedule_cycle = schedule_trace.multi_opportunity_mpc_cycle_result
    rolling_output = rolling_cycle.rolling_headroom_optimization_output
    schedule_output = schedule_cycle.multi_opportunity_optimization_output
    entry = schedule_output.headroom_schedule.entries[0]

    assert full_output.headroom_requirement.required_headroom_energy_kwh == 8.0
    assert (
        rolling_output.rolling_headroom_requirement.headroom_requirement.required_headroom_energy_kwh
        == 3.8
    )
    assert entry.headroom_requirement is not None
    assert entry.required_pre_opportunity_headroom_kwh >= (
        entry.headroom_requirement.required_headroom_energy_kwh
    )
    assert (
        schedule_output.candidate_planning_result.source_input.headroom_schedule
        is schedule_output.headroom_schedule
    )


def test_comparison_exports_deterministic_csv_summary_and_svg_evidence(
    tmp_path: Path,
) -> None:
    first = run_demo(tmp_path)
    comparison = first.comparison_csv_path.read_text(encoding="utf-8")
    summary = first.summary_path.read_text(encoding="utf-8")
    rows = tuple(csv.DictReader(StringIO(comparison)))

    assert len(rows) == 24
    assert {
        "schedule_first_standalone_headroom_kwh",
        "schedule_first_adjusted_headroom_kwh",
        "schedule_opportunity_count",
        "schedule_allowed_grid_charge_kw",
        "schedule_actual_grid_power_kw",
    } <= set(rows[0])
    assert "Schedule-aware is not assumed to be optimal" in summary
    assert all(
        path.exists()
        for path in (
            first.target_svg_path,
            first.required_headroom_svg_path,
            first.soc_svg_path,
            first.grid_svg_path,
        )
    )

    second = run_demo(tmp_path)
    assert second.comparison_csv_path.read_text(encoding="utf-8") == comparison
    assert second.summary_path.read_text(encoding="utf-8") == summary
