"""Tests for the runnable explainable daily MPC demo."""

import csv
from dataclasses import FrozenInstanceError
from io import StringIO
from pathlib import Path
from typing import Any, cast

import pytest

from ems_simulator import demo
from ems_simulator.mpc_demo import (
    _HORIZON_POINTS,
    ExplainableMPCDemoExecutionResult,
    create_demo_input,
    run_demo,
)


def test_demo_input_uses_explicit_aligned_four_point_repeating_horizons(
    tmp_path: Path,
) -> None:
    source = create_demo_input(tmp_path)

    assert len(source.forecast_horizons) == 24
    for hour, horizon in enumerate(source.forecast_horizons):
        assert len(horizon.points) == _HORIZON_POINTS
        assert (
            horizon.points[0].timestamp
            == source.integration_input.daily_input.step_identities[hour].timestamp
        )
    final_horizon = source.forecast_horizons[-1]
    assert final_horizon.points[-1].pv_power_kw == demo.PV_PROFILE_KW[2]
    assert final_horizon.points[-1].load_power_kw == demo.LOAD_PROFILE_KW[2]
    assert (
        final_horizon.points[-1].electricity_price_cny_per_kwh
        == demo.TARIFF_PROFILE_CNY_PER_KWH[2]
    )


def test_demo_generates_explainable_and_simulator_outputs(tmp_path: Path) -> None:
    execution = run_demo(tmp_path)

    assert isinstance(execution, ExplainableMPCDemoExecutionResult)
    expected = {
        "mpc_decisions.csv",
        "simulation_result.csv",
        "power_curve.svg",
        "soc_curve.svg",
        "daily_summary.txt",
    }
    assert {path.name for path in tmp_path.iterdir()} == expected
    assert all(path.stat().st_size > 0 for path in tmp_path.iterdir())
    decision_rows = tuple(
        csv.DictReader(
            StringIO(execution.decision_csv_path.read_text(encoding="utf-8"))
        )
    )
    assert len(decision_rows) == 24
    assert [row["timestamp"] for row in decision_rows] == sorted(
        row["timestamp"] for row in decision_rows
    )
    assert {row["final_action"] for row in decision_rows} == {
        "charge",
        "discharge",
        "idle",
    }
    assert any(row["revision_applied"] == "true" for row in decision_rows)
    assert any("功率" in row["formatted_text"] for row in decision_rows)
    assert all(row["final_battery_horizon_feasible"] == "true" for row in decision_rows)
    simulation_rows = tuple(
        csv.DictReader(
            StringIO(execution.simulation_paths.csv_path.read_text(encoding="utf-8"))
        )
    )
    assert len(simulation_rows) == 24
    assert all(
        0.20 <= trace.state.battery_result.next_state.soc <= 1.0
        for trace in execution.daily_result.simulation_result.traces
    )
    summary = execution.summary_path.read_text(encoding="utf-8")
    for metric in (
        "pv_energy_kwh=",
        "load_energy_kwh=",
        "battery_throughput_kwh=",
        "grid_import_energy_kwh=",
        "grid_export_energy_kwh=",
        "mpc_charge_decisions=",
        "mpc_discharge_decisions=",
        "mpc_idle_decisions=",
        "mpc_revised_decisions=",
        "mpc_soc_limited_decisions=",
        "mpc_power_limited_decisions=",
        "final_soc=",
    ):
        assert metric in summary


def test_demo_repeat_run_overwrites_deterministically_and_result_is_immutable(
    tmp_path: Path,
) -> None:
    first = run_demo(tmp_path)
    first_content = first.decision_csv_path.read_text(encoding="utf-8")
    second = run_demo(tmp_path)

    assert second.decision_csv_path.read_text(encoding="utf-8") == first_content
    assert second.simulation_export.csv_content == first.simulation_export.csv_content
    assert not hasattr(second, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, second).summary_path = tmp_path / "other.txt"


def test_existing_simulator_demo_remains_independent(tmp_path: Path) -> None:
    existing = demo.run_demo(tmp_path)

    assert existing.paths.csv_path.name == "simulation_result.csv"
    assert not (tmp_path / "mpc_decisions.csv").exists()
