"""Structural validation for TASK-146's finite diagnostic comparison demo."""

import csv
from io import StringIO
from pathlib import Path

from ems_simulator.multi_opportunity_headroom_demo import (
    _GAP_TOLERANCE_POINTS,
    LOAD_POWER_PROFILE_KW,
    PV_POWER_PROFILE_KW,
    create_demo_input,
    run_demo,
)


def test_scenario_has_two_separated_pv_surplus_opportunities() -> None:
    surplus = tuple(
        max(pv - load, 0.0)
        for pv, load in zip(PV_POWER_PROFILE_KW, LOAD_POWER_PROFILE_KW, strict=True)
    )

    assert all(value > 0 for value in surplus[8:11])
    assert all(value == 0 for value in surplus[11:14])
    assert len(surplus[11:14]) > _GAP_TOLERANCE_POINTS
    assert all(value > 0 for value in surplus[14:18])


def test_rolling_provenance_selects_first_then_second_then_no_opportunity(
    tmp_path: Path,
) -> None:
    execution = run_demo(tmp_path)
    source = execution.rolling_source_input
    traces = execution.rolling_result.step_traces

    first = traces[
        0
    ].rolling_headroom_mpc_cycle_result.rolling_headroom_optimization_output.rolling_headroom_requirement
    assert tuple(step.source_index for step in first.opportunity_window.steps) == (
        8,
        9,
        10,
    )
    assert len(first.selected_forecast_horizon.points) == 3
    assert all(
        selected is source.forecast_horizons[0].points[index]
        for selected, index in zip(
            first.selected_forecast_horizon.points,
            (8, 9, 10),
            strict=True,
        )
    )

    second = traces[
        11
    ].rolling_headroom_mpc_cycle_result.rolling_headroom_optimization_output.rolling_headroom_requirement
    assert tuple(step.source_index for step in second.opportunity_window.steps) == (
        3,
        4,
        5,
        6,
    )
    assert second.opportunity_window.steps[0].forecast_point.timestamp == (
        source.integration_input.daily_input.step_identities[14].timestamp
    )
    assert not (
        traces[
            18
        ].rolling_headroom_mpc_cycle_result.rolling_headroom_optimization_output.rolling_headroom_requirement.opportunity_window.steps
    )


def test_demo_preserves_shared_inputs_and_exposes_accounting_reservation_effect(
    tmp_path: Path,
) -> None:
    execution = run_demo(tmp_path)
    full_trace = execution.full_result.step_traces[0]
    rolling_trace = execution.rolling_result.step_traces[0]
    full_output = full_trace.headroom_mpc_cycle_result.headroom_optimization_output
    rolling_cycle = rolling_trace.rolling_headroom_mpc_cycle_result
    rolling_output = rolling_cycle.rolling_headroom_optimization_output
    full_requirement = full_output.headroom_requirement
    rolling_requirement = (
        rolling_output.rolling_headroom_requirement.headroom_requirement
    )
    full_reservation = full_output.candidate_planning_result.grid_charge_reservation
    rolling_reservation = (
        rolling_output.candidate_planning_result.grid_charge_reservation
    )

    assert (
        execution.full_source_input.integration_input
        is execution.rolling_source_input.integration_input
    )
    assert (
        execution.full_source_input.forecast_horizons
        is execution.rolling_source_input.forecast_horizons
    )
    assert (
        full_trace.headroom_mpc_cycle_result.source_input.battery_state.soc_fraction
        == rolling_cycle.source_input.battery_state.soc_fraction
    )
    assert full_requirement.required_headroom_energy_kwh > (
        rolling_requirement.required_headroom_energy_kwh
    )
    assert full_requirement.recommended_pre_pv_max_soc_fraction < (
        rolling_requirement.recommended_pre_pv_max_soc_fraction
    )
    assert full_reservation is not None
    assert rolling_reservation is not None
    assert full_reservation.allowed_grid_charge_power_kw < (
        rolling_reservation.allowed_grid_charge_power_kw
    )


def test_demo_exports_deterministic_24_hour_observation_artifacts(
    tmp_path: Path,
) -> None:
    first = run_demo(tmp_path)
    comparison = first.comparison_csv_path.read_text(encoding="utf-8")
    summary = first.summary_path.read_text(encoding="utf-8")

    rows = tuple(csv.DictReader(StringIO(comparison)))
    assert (
        len(first.full_result.step_traces)
        == len(first.rolling_result.step_traces)
        == 24
    )
    assert len(rows) == 24
    assert {
        "full_required_headroom_kwh",
        "rolling_required_headroom_kwh",
        "rolling_selected_source_indexes",
        "full_actual_grid_power_kw",
        "rolling_actual_grid_power_kw",
    } <= set(rows[0])
    assert "This scenario is intentionally diagnostic" in summary
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


def test_demo_input_is_explicitly_finite_and_never_repeats_day_profile(
    tmp_path: Path,
) -> None:
    source = create_demo_input(tmp_path)
    final_horizon = source.forecast_horizons[-1]

    assert len(final_horizon.points) == 24
    assert final_horizon.points[0].pv_power_kw == PV_POWER_PROFILE_KW[-1]
    assert final_horizon.points[1].pv_power_kw == 0.0
    assert final_horizon.points[1].load_power_kw == 0.0
