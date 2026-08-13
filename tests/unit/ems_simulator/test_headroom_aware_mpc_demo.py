"""Tests for the TASK-139 longer-horizon headroom-aware MPC demo."""

import csv
from io import StringIO
from pathlib import Path

from ems_simulator.headroom_aware_mpc_demo import (
    _HORIZON_POINTS,
    HeadroomAwareMPCDemoExecutionResult,
    create_demo_input,
    run_demo,
)


def test_demo_input_uses_24_point_repeating_day_horizons(tmp_path: Path) -> None:
    source = create_demo_input(tmp_path)

    assert source.source_strategy.name == "headroom-aware-net-load-mpc"
    assert source.source_strategy.version == "1.0"
    assert len(source.forecast_horizons) == 24
    assert source.mpc_configuration.forecast_horizon_points == _HORIZON_POINTS
    for hour, horizon in enumerate(source.forecast_horizons):
        assert len(horizon.points) == _HORIZON_POINTS
        assert (
            horizon.points[0].timestamp
            == source.integration_input.daily_input.step_identities[hour].timestamp
        )

    wrapped = source.forecast_horizons[23]
    next_day_midnight = source.forecast_horizons[0].points[0]
    assert wrapped.points[1].pv_power_kw == next_day_midnight.pv_power_kw
    assert wrapped.points[1].load_power_kw == next_day_midnight.load_power_kw
    assert (
        wrapped.points[1].electricity_price_cny_per_kwh
        == next_day_midnight.electricity_price_cny_per_kwh
    )


def test_demo_retains_headroom_evidence_and_generates_all_outputs(
    tmp_path: Path,
) -> None:
    execution = run_demo(tmp_path)

    assert isinstance(execution, HeadroomAwareMPCDemoExecutionResult)
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
    assert all(
        trace.physical_cycle_view is trace.headroom_mpc_cycle_result.physical_cycle_view
        for trace in execution.daily_result.step_traces
    )
    assert all(
        0.20 <= trace.simulation_trace.state.battery_result.next_state.soc <= 1.0
        for trace in execution.daily_result.step_traces
    )
    decisions = tuple(
        csv.DictReader(
            StringIO(execution.decision_csv_path.read_text(encoding="utf-8"))
        )
    )
    assert len(decisions) == 24
    assert {row["strategy_name"] for row in decisions} == {
        "headroom-aware-net-load-mpc"
    }


def test_headroom_reserves_overnight_grid_charge_without_limiting_pv_charge(
    tmp_path: Path,
) -> None:
    execution = run_demo(tmp_path)
    traces = execution.daily_result.step_traces

    overnight = traces[:6]
    assert all(
        trace.headroom_mpc_cycle_result.headroom_optimization_output.candidate_planning_result.grid_charge_reservation
        is not None
        for trace in overnight
    )
    for trace in overnight:
        output = trace.headroom_mpc_cycle_result.headroom_optimization_output
        reservation = output.candidate_planning_result.grid_charge_reservation
        assert reservation is not None
        assert reservation.allowed_grid_charge_power_kw == 0.0
    assert all(
        trace.headroom_mpc_cycle_result.headroom_optimization_output.candidate_planning_result.final_output.solution.steps[
            0
        ].intent.action
        == "idle"
        for trace in overnight
    )

    pv_surplus = tuple(
        trace
        for trace in traces
        if trace.forecast_horizon.points[0].pv_power_kw
        > trace.forecast_horizon.points[0].load_power_kw
    )
    assert pv_surplus
    assert all(
        trace.headroom_mpc_cycle_result.headroom_optimization_output.candidate_planning_result.grid_charge_reservation
        is None
        for trace in pv_surplus
    )
    assert any(
        trace.headroom_mpc_cycle_result.decision.intent.action == "charge"
        for trace in pv_surplus
    )


def test_high_price_discharge_remains_net_load_bounded_and_no_exporting_discharge(
    tmp_path: Path,
) -> None:
    execution = run_demo(tmp_path)

    for trace in execution.daily_result.step_traces:
        point = trace.forecast_horizon.points[0]
        decision = trace.headroom_mpc_cycle_result.decision
        if (
            point.electricity_price_cny_per_kwh is not None
            and point.electricity_price_cny_per_kwh >= 0.90
            and decision.intent.action == "discharge"
        ):
            assert decision.requested_power_kw <= (
                max(point.load_power_kw - point.pv_power_kw, 0.0) + 1e-9
            )
            assert (
                trace.simulation_trace.state.grid_result.actual_grid_power_kw >= -1e-9
            )


def test_demo_repeat_run_has_equivalent_semantic_outputs(tmp_path: Path) -> None:
    first = run_demo(tmp_path)
    first_decisions = first.decision_csv_path.read_text(encoding="utf-8")
    first_simulation = first.simulation_paths.csv_path.read_text(encoding="utf-8")
    first_summary = first.summary_path.read_text(encoding="utf-8")
    second = run_demo(tmp_path)

    assert second.decision_csv_path.read_text(encoding="utf-8") == first_decisions
    assert (
        second.simulation_paths.csv_path.read_text(encoding="utf-8") == first_simulation
    )
    assert second.summary_path.read_text(encoding="utf-8") == first_summary
