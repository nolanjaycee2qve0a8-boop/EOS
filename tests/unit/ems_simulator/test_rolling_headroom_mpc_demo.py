"""Tests for the TASK-145 full versus rolling headroom observation demo."""

import csv
from io import StringIO
from pathlib import Path

from ems_simulator.rolling_headroom_mpc_demo import run_demo


def test_demo_runs_both_existing_daily_paths_with_shared_caller_facts(
    tmp_path: Path,
) -> None:
    execution = run_demo(tmp_path)

    assert len(execution.full_result.step_traces) == 24
    assert len(execution.rolling_result.step_traces) == 24
    assert (
        execution.full_source_input.integration_input
        is execution.rolling_source_input.integration_input
    )
    assert (
        execution.full_source_input.forecast_horizons
        is execution.rolling_source_input.forecast_horizons
    )
    assert len(execution.full_source_input.forecast_horizons[0].points) == 24

    for index, (full_trace, rolling_trace) in enumerate(
        zip(
            execution.full_result.step_traces,
            execution.rolling_result.step_traces,
            strict=True,
        )
    ):
        assert (
            full_trace.forecast_horizon
            is execution.full_source_input.forecast_horizons[index]
        )
        cycle = rolling_trace.rolling_headroom_mpc_cycle_result
        rolling = (
            cycle.rolling_headroom_optimization_output.rolling_headroom_requirement
        )
        assert rolling.source_input.forecast_horizon is rolling_trace.forecast_horizon
        assert tuple(
            step.forecast_point for step in rolling.opportunity_window.steps
        ) == (rolling.selected_forecast_horizon.points)


def test_demo_exports_24_observed_rows_summary_and_comparison_svgs(
    tmp_path: Path,
) -> None:
    execution = run_demo(tmp_path)

    expected = {
        "full_mpc_decisions.csv",
        "rolling_mpc_decisions.csv",
        "headroom_comparison.csv",
        "daily_summary.txt",
        "recommended_soc_target.svg",
        "soc_comparison.svg",
        "grid_power_comparison.svg",
    }
    assert {path.name for path in tmp_path.iterdir()} == expected
    assert all(path.stat().st_size > 0 for path in tmp_path.iterdir())

    rows = tuple(
        csv.DictReader(
            StringIO(execution.comparison_csv_path.read_text(encoding="utf-8"))
        )
    )
    assert len(rows) == 24
    assert {
        "timestamp",
        "full_required_headroom_kwh",
        "rolling_opportunity_indexes",
        "rolling_required_headroom_kwh",
        "full_actual_grid_power_kw",
        "rolling_actual_grid_power_kw",
    } <= set(rows[0])
    assert (
        "Rolling is not automatically better; this demo reports observed behavior."
        in (execution.summary_path.read_text(encoding="utf-8"))
    )
    for path in (
        execution.target_svg_path,
        execution.soc_svg_path,
        execution.grid_svg_path,
    ):
        assert '<svg xmlns="http://www.w3.org/2000/svg"' in path.read_text(
            encoding="utf-8"
        )


def test_demo_repeat_run_is_deterministic(tmp_path: Path) -> None:
    first = run_demo(tmp_path)
    comparison = first.comparison_csv_path.read_text(encoding="utf-8")
    summary = first.summary_path.read_text(encoding="utf-8")
    target_svg = first.target_svg_path.read_text(encoding="utf-8")

    second = run_demo(tmp_path)

    assert second.comparison_csv_path.read_text(encoding="utf-8") == comparison
    assert second.summary_path.read_text(encoding="utf-8") == summary
    assert second.target_svg_path.read_text(encoding="utf-8") == target_svg
