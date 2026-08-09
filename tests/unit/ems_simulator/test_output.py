"""Tests for deterministic CSV, visualization, and daily summary outputs."""

import csv
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from xml.etree import ElementTree

import pytest

from ems_simulator import (
    BatteryParameters,
    DailySimulationResult,
    DailySimulationRunner,
    DailySimulationScenarioInput,
    SimulationResultExporter,
)
from simulator import SimulationStepIdentity


def make_result() -> DailySimulationResult:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    step_identities = tuple(
        SimulationStepIdentity(
            hour,
            3600.0,
            start + timedelta(hours=hour),
        )
        for hour in range(24)
    )
    source_input = DailySimulationScenarioInput(
        step_identities=step_identities,
        pv_power_curve_kw=(0.0,) * 6 + (5.0,) * 12 + (0.0,) * 6,
        load_power_curve_kw=(2.0,) * 24,
        tariff_curve_cny_per_kwh=(0.5,) * 24,
        battery_parameters=BatteryParameters(
            capacity_kwh=10.0,
            max_charge_power_kw=3.0,
            max_discharge_power_kw=3.0,
            charge_efficiency=0.95,
            discharge_efficiency=0.9,
            reserve_soc=0.2,
        ),
        initial_soc=0.5,
    )
    return DailySimulationRunner.run(source_input)


def test_csv_content_preserves_timestamp_order_and_observed_values() -> None:
    result = make_result()

    export = SimulationResultExporter.export(result)
    rows = tuple(csv.DictReader(StringIO(export.csv_content)))

    assert export.source_result is result
    assert len(rows) == 24
    assert tuple(rows[0]) == (
        "timestamp",
        "pv_power_kw",
        "load_power_kw",
        "battery_power_kw",
        "grid_power_kw",
        "soc",
    )
    for index, (row, trace) in enumerate(zip(rows, result.traces, strict=True)):
        timestamp = trace.simulation_input.step_identity.timestamp
        assert timestamp is not None
        assert row["timestamp"] == timestamp.isoformat()
        assert timestamp == result.source_input.step_identities[index].timestamp
        assert float(row["pv_power_kw"]) == trace.state.pv_result.actual_power_kw
        assert float(row["load_power_kw"]) == trace.state.load_result.actual_power_kw
        assert (
            float(row["battery_power_kw"]) == trace.state.battery_result.actual_power_kw
        )
        assert (
            float(row["grid_power_kw"]) == trace.state.grid_result.actual_grid_power_kw
        )
        assert float(row["soc"]) == trace.state.battery_result.next_state.soc


def test_daily_summary_uses_step_duration_and_signed_grid_separation() -> None:
    result = make_result()

    summary = SimulationResultExporter.export(result).summary

    expected_pv = sum(trace.state.pv_result.actual_power_kw for trace in result.traces)
    expected_load = sum(
        trace.state.load_result.actual_power_kw for trace in result.traces
    )
    expected_throughput = sum(
        abs(trace.state.battery_result.actual_power_kw) for trace in result.traces
    )
    expected_import = sum(
        max(0.0, trace.state.grid_result.actual_grid_power_kw)
        for trace in result.traces
    )
    expected_export = sum(
        max(0.0, -trace.state.grid_result.actual_grid_power_kw)
        for trace in result.traces
    )

    assert summary.source_result is result
    assert summary.pv_energy_kwh == expected_pv
    assert summary.load_energy_kwh == expected_load
    assert summary.battery_throughput_kwh == expected_throughput
    assert summary.grid_import_energy_kwh == pytest.approx(expected_import)
    assert summary.grid_export_energy_kwh == pytest.approx(expected_export)


def test_visualization_contains_power_and_soc_curves() -> None:
    result = make_result()

    visualization = SimulationResultExporter.export(result).visualization

    assert visualization.source_result is result
    assert visualization.power_curve_svg.startswith("<svg")
    assert visualization.power_curve_svg.endswith("</svg>\n")
    assert 'data-series="PV"' in visualization.power_curve_svg
    assert 'data-series="Load"' in visualization.power_curve_svg
    assert 'data-series="Battery"' in visualization.power_curve_svg
    assert 'data-series="Grid"' in visualization.power_curve_svg
    assert visualization.soc_curve_svg.startswith("<svg")
    assert 'data-series="SOC"' in visualization.soc_curve_svg
    assert visualization.soc_curve_svg.endswith("</svg>\n")
    assert ElementTree.fromstring(visualization.power_curve_svg).tag.endswith("svg")
    assert ElementTree.fromstring(visualization.soc_curve_svg).tag.endswith("svg")


def test_export_is_deterministic_and_does_not_mutate_result() -> None:
    result = make_result()
    original_traces = result.traces
    original_states = tuple(trace.state for trace in result.traces)

    first = SimulationResultExporter.export(result)
    second = SimulationResultExporter.export(result)

    assert first is not second
    assert first.source_result is result
    assert second.source_result is result
    assert first.csv_content == second.csv_content
    assert first.summary == second.summary
    assert first.visualization.power_curve_svg == second.visualization.power_curve_svg
    assert first.visualization.soc_curve_svg == second.visualization.soc_curve_svg
    assert result.traces is original_traces
    assert all(
        trace.state is original_states[index]
        for index, trace in enumerate(result.traces)
    )


def test_write_files_uses_fixed_names_and_exact_rendered_content(
    tmp_path: Path,
) -> None:
    export = SimulationResultExporter.export(make_result())

    paths = SimulationResultExporter.write_files(export, tmp_path)

    assert paths.csv_path == tmp_path / "simulation_result.csv"
    assert paths.power_curve_path == tmp_path / "power_curve.svg"
    assert paths.soc_curve_path == tmp_path / "soc_curve.svg"
    assert paths.csv_path.read_text(encoding="utf-8") == export.csv_content
    assert (
        paths.power_curve_path.read_text(encoding="utf-8")
        == export.visualization.power_curve_svg
    )
    assert (
        paths.soc_curve_path.read_text(encoding="utf-8")
        == export.visualization.soc_curve_svg
    )


def test_export_artifacts_are_frozen_and_slotted() -> None:
    export = SimulationResultExporter.export(make_result())

    assert not hasattr(export, "__dict__")
    assert not hasattr(export.summary, "__dict__")
    assert not hasattr(export.visualization, "__dict__")
    with pytest.raises(FrozenInstanceError):
        export.csv_content = ""  # type: ignore[misc]


def test_exporter_rejects_invalid_inputs(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="DailySimulationResult"):
        SimulationResultExporter.export(object())  # type: ignore[arg-type]

    export = SimulationResultExporter.export(make_result())
    with pytest.raises(TypeError, match="DailySimulationExport"):
        SimulationResultExporter.write_files(object(), tmp_path)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match=r"pathlib\.Path"):
        SimulationResultExporter.write_files(export, str(tmp_path))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="existing directory"):
        SimulationResultExporter.write_files(export, tmp_path / "missing")
