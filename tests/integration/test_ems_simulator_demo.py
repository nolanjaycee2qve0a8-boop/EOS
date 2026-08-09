"""Integration validation for the runnable EOS EMS Simulator 1.0 Demo."""

import csv
from dataclasses import FrozenInstanceError
from io import StringIO
from pathlib import Path

import pytest

from ems_simulator.demo import (
    LOAD_PROFILE_KW,
    PV_PROFILE_KW,
    TARIFF_PROFILE_CNY_PER_KWH,
    create_demo_scenario,
    main,
    run_demo,
)


def test_demo_scenario_contains_explicit_household_facts() -> None:
    scenario = create_demo_scenario()

    assert scenario.pv_power_curve_kw is PV_PROFILE_KW
    assert scenario.load_power_curve_kw is LOAD_PROFILE_KW
    assert scenario.tariff_curve_cny_per_kwh is TARIFF_PROFILE_CNY_PER_KWH
    assert len(scenario.step_identities) == 24
    assert scenario.initial_soc == 0.5
    assert scenario.battery_parameters.capacity_kwh == 10.0
    assert scenario.battery_parameters.reserve_soc == 0.2


def test_demo_runs_24_steps_and_generates_all_outputs(tmp_path: Path) -> None:
    output_directory = tmp_path / "demo"

    execution = run_demo(output_directory)

    assert execution.simulation_result.source_input is execution.source_input
    assert execution.export.source_result is execution.simulation_result
    assert len(execution.simulation_result.traces) == 24
    assert len(execution.simulation_result.progressions) == 23
    assert execution.paths.csv_path.is_file()
    assert execution.paths.power_curve_path.is_file()
    assert execution.paths.soc_curve_path.is_file()
    assert execution.summary_path.is_file()

    rows = tuple(csv.DictReader(StringIO(execution.paths.csv_path.read_text())))
    assert len(rows) == 24
    assert rows[0]["timestamp"] == "2026-01-01T00:00:00+00:00"
    assert rows[-1]["timestamp"] == "2026-01-01T23:00:00+00:00"


def test_demo_summary_and_curves_explain_completed_result(tmp_path: Path) -> None:
    execution = run_demo(tmp_path / "demo")
    summary = execution.export.summary
    summary_text = execution.summary_path.read_text(encoding="utf-8")

    assert f"pv_energy_kwh={summary.pv_energy_kwh:.6f}" in summary_text
    assert f"load_energy_kwh={summary.load_energy_kwh:.6f}" in summary_text
    assert (
        f"battery_throughput_kwh={summary.battery_throughput_kwh:.6f}" in summary_text
    )
    assert (
        f"grid_import_energy_kwh={summary.grid_import_energy_kwh:.6f}" in summary_text
    )
    assert (
        f"grid_export_energy_kwh={summary.grid_export_energy_kwh:.6f}" in summary_text
    )
    assert 'data-series="PV"' in execution.paths.power_curve_path.read_text()
    assert 'data-series="Load"' in execution.paths.power_curve_path.read_text()
    assert 'data-series="Battery"' in execution.paths.power_curve_path.read_text()
    assert 'data-series="Grid"' in execution.paths.power_curve_path.read_text()
    assert 'data-series="SOC"' in execution.paths.soc_curve_path.read_text()


def test_demo_is_deterministic_across_repeated_runs(tmp_path: Path) -> None:
    first = run_demo(tmp_path / "first")
    second = run_demo(tmp_path / "second")

    assert first.paths.csv_path.read_bytes() == second.paths.csv_path.read_bytes()
    assert (
        first.paths.power_curve_path.read_bytes()
        == second.paths.power_curve_path.read_bytes()
    )
    assert (
        first.paths.soc_curve_path.read_bytes()
        == second.paths.soc_curve_path.read_bytes()
    )
    assert first.summary_path.read_bytes() == second.summary_path.read_bytes()
    assert (
        first.export.summary.pv_energy_kwh,
        first.export.summary.load_energy_kwh,
        first.export.summary.battery_throughput_kwh,
        first.export.summary.grid_import_energy_kwh,
        first.export.summary.grid_export_energy_kwh,
    ) == (
        second.export.summary.pv_energy_kwh,
        second.export.summary.load_energy_kwh,
        second.export.summary.battery_throughput_kwh,
        second.export.summary.grid_import_energy_kwh,
        second.export.summary.grid_export_energy_kwh,
    )


def test_demo_execution_result_is_frozen_and_slotted(tmp_path: Path) -> None:
    execution = run_demo(tmp_path / "demo")

    assert not hasattr(execution, "__dict__")
    with pytest.raises(FrozenInstanceError):
        execution.summary_path = tmp_path / "other"  # type: ignore[misc]


def test_demo_cli_runs_with_one_command(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_directory = tmp_path / "cli-demo"

    exit_code = main(("--output-dir", str(output_directory)))

    assert exit_code == 0
    assert (output_directory / "simulation_result.csv").is_file()
    assert (output_directory / "power_curve.svg").is_file()
    assert (output_directory / "soc_curve.svg").is_file()
    assert (output_directory / "daily_summary.txt").is_file()
    output = capsys.readouterr().out
    assert "simulation_result.csv" in output
    assert "daily_summary.txt" in output


def test_demo_rejects_invalid_output_directory_type() -> None:
    with pytest.raises(TypeError, match=r"pathlib\.Path"):
        run_demo("demo")  # type: ignore[arg-type]
