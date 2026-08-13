"""Tests for the TASK-131 net-load-aware explainable MPC comparison demo."""

import csv
from io import StringIO
from pathlib import Path

import pytest

from ems_simulator.net_load_mpc_demo import (
    _HORIZON_POINTS,
    NetLoadAwareMPCDemoExecutionResult,
    create_demo_input,
    run_demo,
)


def test_demo_input_uses_the_existing_scenario_with_a_distinct_strategy(
    tmp_path: Path,
) -> None:
    source = create_demo_input(tmp_path)

    assert source.source_strategy.name == "physically-aware-net-load-mpc"
    assert source.source_strategy.version == "1.0"
    assert len(source.forecast_horizons) == 24
    for hour, horizon in enumerate(source.forecast_horizons):
        assert len(horizon.points) == _HORIZON_POINTS
        assert (
            horizon.points[0].timestamp
            == source.integration_input.daily_input.step_identities[hour].timestamp
        )
    daily_input = source.integration_input.daily_input
    assert daily_input.initial_soc == 0.50
    assert daily_input.battery_parameters.capacity_kwh == 10.0
    assert daily_input.battery_parameters.reserve_soc == 0.20


def test_demo_generates_complete_net_load_aware_evidence_and_outputs(
    tmp_path: Path,
) -> None:
    execution = run_demo(tmp_path)

    assert isinstance(execution, NetLoadAwareMPCDemoExecutionResult)
    assert {path.name for path in tmp_path.iterdir()} == {
        "mpc_decisions.csv",
        "simulation_result.csv",
        "power_curve.svg",
        "soc_curve.svg",
        "daily_summary.txt",
    }
    assert all(path.stat().st_size > 0 for path in tmp_path.iterdir())
    assert len(execution.daily_result.step_traces) == 24
    assert len(execution.daily_result.journal_records) == 24
    assert len(execution.daily_result.csv_rows) == 24
    decision_rows = tuple(
        csv.DictReader(
            StringIO(execution.decision_csv_path.read_text(encoding="utf-8"))
        )
    )
    assert len(decision_rows) == 24
    assert {row["strategy_name"] for row in decision_rows} == {
        "physically-aware-net-load-mpc"
    }
    assert all(
        0.20 <= trace.state.battery_result.next_state.soc <= 1.0
        for trace in execution.daily_result.simulation_result.traces
    )


def test_high_price_net_load_candidates_preserve_surplus_and_deficit_semantics(
    tmp_path: Path,
) -> None:
    execution = run_demo(tmp_path)

    for trace in execution.daily_result.step_traces:
        point = trace.forecast_horizon.points[0]
        explanation = trace.explanation
        if point.electricity_price_cny_per_kwh is not None and (
            point.electricity_price_cny_per_kwh >= 0.90
        ):
            if point.pv_power_kw > point.load_power_kw:
                assert explanation.candidate_action.action == "charge"
                assert explanation.candidate_requested_power_kw == pytest.approx(
                    point.pv_power_kw - point.load_power_kw
                )
            elif point.load_power_kw > point.pv_power_kw:
                assert explanation.candidate_action.action == "discharge"
                assert explanation.candidate_requested_power_kw == pytest.approx(
                    point.load_power_kw - point.pv_power_kw
                )

    sixteen = execution.daily_result.step_traces[16].explanation
    assert sixteen.candidate_action.action == "charge"
    assert sixteen.candidate_requested_power_kw == pytest.approx(0.6)
    assert sixteen.final_action.action == "idle"
    assert sixteen.physical_explanation.revision_reasons == ("max_soc_limit",)

    seventeen = execution.daily_result.step_traces[17].explanation
    assert seventeen.candidate_action.action == "discharge"
    assert seventeen.candidate_requested_power_kw == pytest.approx(1.2)
    assert seventeen.final_action.action == "discharge"
    assert seventeen.final_requested_power_kw == pytest.approx(1.2)


def test_demo_repeat_run_has_equivalent_semantic_outputs(tmp_path: Path) -> None:
    first = run_demo(tmp_path)
    first_decisions = first.decision_csv_path.read_text(encoding="utf-8")
    first_simulation = first.simulation_paths.csv_path.read_text(encoding="utf-8")
    second = run_demo(tmp_path)

    assert second.decision_csv_path.read_text(encoding="utf-8") == first_decisions
    assert (
        second.simulation_paths.csv_path.read_text(encoding="utf-8") == first_simulation
    )
