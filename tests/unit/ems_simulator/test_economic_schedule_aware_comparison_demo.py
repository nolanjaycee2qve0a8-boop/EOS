"""Focused behavioural measurements for TASK-161's read-only A/B demo."""

from pathlib import Path

import pytest

from ems_simulator.economic_multi_opportunity_explainable_mpc_daily import (
    EconomicMultiOpportunityExplainableMPCDailySimulationResult,
    EconomicMultiOpportunityExplainableMPCDailySimulationStepTrace,
)
from ems_simulator.economic_schedule_aware_comparison_demo import (
    run_comparison,
    scenario_matrix,
)
from optimization import EconomicGridChargeValueResult, EconomicShiftClassification


def _value_results(
    result: EconomicMultiOpportunityExplainableMPCDailySimulationResult,
) -> tuple[EconomicGridChargeValueResult, ...]:
    return tuple(
        value
        for trace in result.step_traces
        if (value := _economic_value(trace)) is not None
    )


def _economic_value(
    trace: EconomicMultiOpportunityExplainableMPCDailySimulationStepTrace,
) -> EconomicGridChargeValueResult | None:
    return trace.economic_multi_opportunity_mpc_cycle_result.economic_multi_opportunity_optimization_output.candidate_planning_result.economic_value_result  # noqa: E501


def test_matrix_runs_both_existing_paths_with_exact_shared_facts(
    tmp_path: Path,
) -> None:
    execution = run_comparison(tmp_path)

    assert tuple(scenario.scenario_id for scenario in scenario_matrix()) == (
        "E0",
        "E1",
        "E2",
    )
    assert len(execution.scenario_results) == 3
    for item in execution.scenario_results:
        schedule_daily = item.schedule_input.daily_mpc_input
        economic_daily = item.economic_input.daily_mpc_input
        assert len(item.schedule_result.step_traces) == 24
        assert len(item.economic_result.step_traces) == 24
        assert schedule_daily.integration_input is economic_daily.integration_input
        assert schedule_daily.forecast_horizons is economic_daily.forecast_horizons
        assert (
            schedule_daily.battery_optimization_model
            is economic_daily.battery_optimization_model
        )
        assert schedule_daily.source_strategy is economic_daily.source_strategy
        assert (
            item.schedule_input.candidate_configuration
            is item.economic_input.candidate_configuration
        )
        assert (
            item.schedule_input.opportunity_configuration
            is item.economic_input.opportunity_configuration
        )


def test_economic_evidence_has_required_positive_negative_and_break_even_gates(
    tmp_path: Path,
) -> None:
    execution = run_comparison(tmp_path)
    results = {item.scenario.scenario_id: item for item in execution.scenario_results}
    expected = {
        "E0": EconomicShiftClassification.POSITIVE,
        "E1": EconomicShiftClassification.NEGATIVE,
        "E2": EconomicShiftClassification.BREAK_EVEN,
    }

    for scenario_id, classification in expected.items():
        values = _value_results(results[scenario_id].economic_result)
        selected = tuple(
            value for value in values if value.economic_classification is classification
        )
        assert selected
        assert all(
            value.economically_supported_grid_charge_power_kw
            <= value.headroom_allowed_grid_charge_power_kw
            for value in selected
        )
        if classification is EconomicShiftClassification.POSITIVE:
            assert any(
                value.headroom_allowed_grid_charge_power_kw > 0.0 for value in selected
            )
            assert all(
                value.economically_supported_grid_charge_power_kw
                == value.headroom_allowed_grid_charge_power_kw
                for value in selected
            )
        else:
            assert any(
                value.headroom_allowed_grid_charge_power_kw > 0.0 for value in selected
            )
            assert all(
                value.economically_supported_grid_charge_power_kw == 0.0
                for value in selected
            )

    assert (
        results[
            "E1"
        ].economic_evidence_metrics.economically_suppressed_grid_charge_energy_kwh
        > 0.0
    )
    assert (
        results[
            "E2"
        ].economic_evidence_metrics.economically_suppressed_grid_charge_energy_kwh
        > 0.0
    )


def test_pv_surplus_bypasses_economic_grid_charge_gating_and_cost_uses_actual_grid(
    tmp_path: Path,
) -> None:
    execution = run_comparison(tmp_path)
    e1 = next(
        item for item in execution.scenario_results if item.scenario.scenario_id == "E1"
    )

    pv_surplus_traces = tuple(
        trace
        for trace in e1.economic_result.step_traces
        if trace.simulation_trace.state.pv_result.actual_power_kw
        > trace.simulation_trace.state.load_result.actual_power_kw
    )
    assert pv_surplus_traces
    assert all(_economic_value(trace) is None for trace in pv_surplus_traces)

    observed_cost = sum(
        max(trace.simulation_trace.state.grid_result.actual_grid_power_kw, 0.0)
        * trace.simulation_trace.simulation_input.step_identity.duration_seconds
        / 3600.0
        * trace.simulation_trace.state.tariff_result.import_price_cny_per_kwh
        for trace in e1.economic_result.step_traces
    )
    assert observed_cost == pytest.approx(e1.economic_metrics.grid_import_cost)
    assert e1.economic_metrics.grid_import_cost < e1.schedule_metrics.grid_import_cost


def test_exported_measurements_are_deterministic(tmp_path: Path) -> None:
    first = run_comparison(tmp_path / "first")
    second = run_comparison(tmp_path / "second")

    first_paths = (
        first.comparison_csv_path,
        first.scenario_summary_path,
        first.daily_summary_path,
        first.grid_import_cost_svg_path,
        first.suppressed_charge_svg_path,
        first.soc_e1_svg_path,
        first.grid_e1_svg_path,
    )
    second_paths = (
        second.comparison_csv_path,
        second.scenario_summary_path,
        second.daily_summary_path,
        second.grid_import_cost_svg_path,
        second.suppressed_charge_svg_path,
        second.soc_e1_svg_path,
        second.grid_e1_svg_path,
    )
    assert all(
        left.read_text(encoding="utf-8") == right.read_text(encoding="utf-8")
        for left, right in zip(first_paths, second_paths, strict=True)
    )
