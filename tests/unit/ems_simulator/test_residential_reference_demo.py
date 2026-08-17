"""TASK-175 deterministic Residential EMS reference demo tests."""

from math import isclose
from pathlib import Path

from ems_simulator.economic_multi_opportunity_explainable_mpc_daily import (
    EconomicMultiOpportunityExplainableMPCDailySimulationResult,
    EconomicMultiOpportunityExplainableMPCDailySimulationStepTrace,
)
from ems_simulator.multi_opportunity_explainable_mpc_daily import (
    MultiOpportunityExplainableMPCDailySimulationResult,
    MultiOpportunityExplainableMPCDailySimulationStepTrace,
)
from ems_simulator.residential_reference_demo import run_residential_reference_demo


def test_reference_demo_reuses_fair_facts_and_actual_simulator_feedback(
    tmp_path: Path,
) -> None:
    result = run_residential_reference_demo(tmp_path / "reference")
    schedule_daily = result.schedule_input.daily_mpc_input
    economic_daily = result.economic_input.daily_mpc_input

    assert schedule_daily.integration_input is economic_daily.integration_input
    assert schedule_daily.forecast_horizons is economic_daily.forecast_horizons
    assert (
        schedule_daily.battery_optimization_model
        is economic_daily.battery_optimization_model
    )
    assert len(result.schedule.result.step_traces) == 24
    assert len(result.economic.result.step_traces) == 24
    for completed in (result.schedule.result, result.economic.result):
        if isinstance(completed, MultiOpportunityExplainableMPCDailySimulationResult):
            _assert_actual_trace_invariants_schedule(completed.step_traces)
        else:
            assert isinstance(
                completed,
                EconomicMultiOpportunityExplainableMPCDailySimulationResult,
            )
            _assert_actual_trace_invariants_economic(completed.step_traces)


def test_reference_demo_builds_two_reconciling_ledgers_and_task174_comparison(
    tmp_path: Path,
) -> None:
    result = run_residential_reference_demo(tmp_path / "reference")
    for path in (result.schedule, result.economic):
        ledger = path.ledger
        assert len(ledger.intervals) == 24
        assert isclose(
            ledger.adjusted_net_economic_cost,
            ledger.extended_outcome_evidence.adjusted_net_economic_cost,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
    explanation = result.comparison
    assert (
        explanation.reference_outcome
        is result.schedule.ledger.extended_outcome_evidence
    )
    assert (
        explanation.candidate_outcome
        is result.economic.ledger.extended_outcome_evidence
    )
    assert isclose(
        explanation.delta_adjusted_cost,
        explanation.import_cost_contribution
        + explanation.export_revenue_contribution
        + explanation.degradation_cost_contribution
        + explanation.terminal_value_contribution,
        rel_tol=0.0,
        abs_tol=1e-12,
    )


def test_reference_demo_outputs_and_repeat_runs_are_deterministic(
    tmp_path: Path,
) -> None:
    first = run_residential_reference_demo(tmp_path / "first")
    second = run_residential_reference_demo(tmp_path / "second")
    first_files = (
        first.timeseries_csv_path,
        first.summary_csv_path,
        first.comparison_csv_path,
        first.explanation_path,
        first.power_svg_path,
        first.soc_svg_path,
        first.tariff_svg_path,
        first.economic_components_svg_path,
    )
    second_files = (
        second.timeseries_csv_path,
        second.summary_csv_path,
        second.comparison_csv_path,
        second.explanation_path,
        second.power_svg_path,
        second.soc_svg_path,
        second.tariff_svg_path,
        second.economic_components_svg_path,
    )
    assert all(path.is_file() for path in first_files)
    assert [path.read_bytes() for path in first_files] == [
        path.read_bytes() for path in second_files
    ]
    explanation = first.explanation_path.read_text(encoding="utf-8")
    for section in (
        "Residential Reference Scenario",
        "System Configuration",
        "Forecast Assumptions",
        "Control Behavior",
        "Energy Results",
        "Economic Results",
        "Economic vs Schedule Comparison",
        "Representative Decision Explanations",
        "Known Limitations",
    ):
        assert section in explanation


def _assert_actual_trace_invariants_schedule(
    traces: tuple[MultiOpportunityExplainableMPCDailySimulationStepTrace, ...],
) -> None:
    for index, trace in enumerate(traces):
        _assert_trace_invariants(trace, traces[index - 1] if index else None)


def _assert_actual_trace_invariants_economic(
    traces: tuple[EconomicMultiOpportunityExplainableMPCDailySimulationStepTrace, ...],
) -> None:
    for index, trace in enumerate(traces):
        _assert_trace_invariants(trace, traces[index - 1] if index else None)


def _assert_trace_invariants(
    trace: MultiOpportunityExplainableMPCDailySimulationStepTrace
    | EconomicMultiOpportunityExplainableMPCDailySimulationStepTrace,
    previous: MultiOpportunityExplainableMPCDailySimulationStepTrace
    | EconomicMultiOpportunityExplainableMPCDailySimulationStepTrace
    | None,
) -> None:
    state = trace.simulation_trace.state
    battery = state.battery_result.actual_power_kw
    assert 0.20 <= state.battery_result.next_state.soc <= 1.0
    assert -3.0 <= battery <= 3.0
    assert isclose(
        state.pv_result.actual_power_kw
        + state.grid_result.actual_grid_power_kw
        - battery,
        state.load_result.actual_power_kw,
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    if previous is not None:
        previous_state = previous.simulation_trace.state
        facts = trace.context.source_context
        assert facts.soc == previous_state.battery_result.next_state.soc
        assert facts.grid_power_kw == previous_state.grid_result.actual_grid_power_kw
