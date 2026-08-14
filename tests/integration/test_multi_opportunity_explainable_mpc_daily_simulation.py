"""Integration tests for finite schedule-aware explainable daily simulation."""

import ast
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, ClassVar, cast

import pytest

from ems_simulator import (
    MultiOpportunityExplainableMPCDailySimulationInput,
    MultiOpportunityExplainableMPCDailySimulationResult,
    MultiOpportunityExplainableMPCDailySimulationRunner,
)
from ems_strategy import (
    FirstStepMPCCurrentActionExtractor,
    MultiOpportunityMPCCycleBoundary,
    MultiOpportunityMPCCycleInput,
    MultiOpportunityMPCCycleResult,
    MultiOpportunitySingleMPCCycleOrchestrator,
)
from optimization import (
    DeterministicBatteryHorizonConstraintAggregator,
    DeterministicBatteryPowerHorizonConstraintEvaluator,
    DeterministicBatterySOCHorizonConstraintEvaluator,
    DeterministicBatterySOCHorizonProjector,
    DeterministicExplicitCandidatePhysicalReviser,
    DeterministicMultiOpportunityCandidatePlanner,
    DeterministicMultiOpportunityGridChargeReservationCalculator,
    DeterministicMultiOpportunityHeadroomScheduleCalculator,
    DeterministicMultiOpportunityPhysicalOptimizer,
    DeterministicPVHeadroomRequirementCalculator,
    DeterministicPVOpportunitySequenceCalculator,
    MultiOpportunityPhysicalOptimizationBoundary,
    NetLoadAwareBaselineOptimizationConfiguration,
    NetLoadAwareBaselineOptimizer,
    OptimizationSolutionControlPlanBuilder,
    PVOpportunityWindowConfiguration,
)
from tests.integration.test_explainable_mpc_daily_simulation import (
    _CountingExplanationBuilder,
    _CountingFileExporter,
    _CountingFormatter,
    _CountingJournalBuilder,
    _CountingRowMapper,
    _CountingSerializer,
    _DecisionTranslator,
    _PassThroughFeasibility,
    _SimulationHandoff,
    _source_input,
)

CANDIDATE_CONFIGURATION = NetLoadAwareBaselineOptimizationConfiguration(0.3, 0.8, 4.0)
OPPORTUNITY_CONFIGURATION = PVOpportunityWindowConfiguration(1)


class _CountingMultiOpportunityCycle(MultiOpportunityMPCCycleBoundary):
    __slots__ = ("_delegate",)
    calls: ClassVar[int] = 0
    fail_on_call: ClassVar[int | None] = None

    def __init__(self, delegate: MultiOpportunityMPCCycleBoundary) -> None:
        self._delegate = delegate

    def run_cycle(
        self, cycle_input: MultiOpportunityMPCCycleInput
    ) -> MultiOpportunityMPCCycleResult:
        self.__class__.calls += 1
        if self.__class__.fail_on_call == self.__class__.calls:
            raise RuntimeError("planned multi-opportunity cycle failure")
        return self._delegate.run_cycle(cycle_input)


@pytest.fixture(autouse=True)
def _reset_counts() -> None:
    _CountingMultiOpportunityCycle.calls = 0
    _CountingMultiOpportunityCycle.fail_on_call = None
    for dependency in (
        _CountingExplanationBuilder,
        _CountingFormatter,
        _CountingJournalBuilder,
        _CountingRowMapper,
        _CountingSerializer,
        _CountingFileExporter,
        _PassThroughFeasibility,
        _SimulationHandoff,
    ):
        dependency.calls = 0


def _cycle() -> MultiOpportunitySingleMPCCycleOrchestrator:
    optimization: MultiOpportunityPhysicalOptimizationBoundary = (
        DeterministicMultiOpportunityPhysicalOptimizer(
            DeterministicMultiOpportunityHeadroomScheduleCalculator(
                DeterministicPVOpportunitySequenceCalculator(),
                DeterministicPVHeadroomRequirementCalculator(),
            ),
            DeterministicMultiOpportunityCandidatePlanner(
                NetLoadAwareBaselineOptimizer(CANDIDATE_CONFIGURATION),
                DeterministicMultiOpportunityGridChargeReservationCalculator(),
            ),
            DeterministicExplicitCandidatePhysicalReviser(
                DeterministicBatterySOCHorizonProjector(),
                DeterministicBatterySOCHorizonConstraintEvaluator(),
                DeterministicBatteryPowerHorizonConstraintEvaluator(),
                DeterministicBatteryHorizonConstraintAggregator(),
            ),
        )
    )
    return MultiOpportunitySingleMPCCycleOrchestrator(
        optimization,
        OptimizationSolutionControlPlanBuilder(),
        FirstStepMPCCurrentActionExtractor(),
        _DecisionTranslator(),
    )


def _runner(
    cycle: MultiOpportunityMPCCycleBoundary | None = None,
) -> MultiOpportunityExplainableMPCDailySimulationRunner:
    return MultiOpportunityExplainableMPCDailySimulationRunner(
        cycle or _CountingMultiOpportunityCycle(_cycle()),
        _CountingExplanationBuilder(),
        _CountingFormatter(),
        _CountingJournalBuilder(),
        _CountingRowMapper(),
        _CountingSerializer(),
        _CountingFileExporter(),
        _PassThroughFeasibility(),
        _SimulationHandoff(),
    )


def _source(tmp_path: Path) -> MultiOpportunityExplainableMPCDailySimulationInput:
    return MultiOpportunityExplainableMPCDailySimulationInput(
        _source_input(tmp_path / "multi_opportunity_decisions.csv"),
        CANDIDATE_CONFIGURATION,
        OPPORTUNITY_CONFIGURATION,
    )


def test_daily_runner_preserves_actual_feedback_and_outer_provenance(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    result = _runner().run(source)
    daily_mpc_input = source.daily_mpc_input

    assert isinstance(result, MultiOpportunityExplainableMPCDailySimulationResult)
    assert (
        len(result.step_traces)
        == len(result.journal_records)
        == len(result.csv_rows)
        == 24
    )
    assert _CountingMultiOpportunityCycle.calls == 24
    assert (
        _CountingExplanationBuilder.calls,
        _CountingFormatter.calls,
        _CountingJournalBuilder.calls,
        _CountingRowMapper.calls,
        _PassThroughFeasibility.calls,
        _SimulationHandoff.calls,
    ) == (24, 24, 24, 24, 24, 24)
    assert (_CountingSerializer.calls, _CountingFileExporter.calls) == (1, 1)
    assert daily_mpc_input.decision_csv_output_path.read_text(encoding="utf-8") == (
        result.csv_content
    )

    for index, trace in enumerate(result.step_traces):
        cycle = trace.multi_opportunity_mpc_cycle_result
        output = cycle.multi_opportunity_optimization_output
        assert trace.forecast_horizon is daily_mpc_input.forecast_horizons[index]
        assert (
            trace.context is cycle.source_input.physical_cycle_input.cycle_input.context
        )
        assert trace.physical_cycle_view is cycle.physical_cycle_view
        assert cycle.decision is trace.physical_cycle_view.decision
        assert trace.explanation.source_input.cycle_result is trace.physical_cycle_view
        assert (
            trace.journal_record.source_input.cycle_result is trace.physical_cycle_view
        )
        assert trace.decision_provenance.decision is cycle.decision
        assert trace.feasible_decision.source_decision is cycle.decision
        assert trace.handoff.source_feasible_decision is trace.feasible_decision
        assert (
            trace.simulation_trace.simulation_input.battery_input.actuation
            is trace.handoff.actuation
        )
        assert output.source_input.problem.forecast_horizon is trace.forecast_horizon
        assert (
            output.headroom_schedule.source_input.forecast_horizon
            is trace.forecast_horizon
        )
        assert (
            output.physical_output.candidate_output
            is output.candidate_planning_result.final_output
        )
        if index == 0:
            assert (
                cycle.source_input.physical_cycle_input.battery_state.soc_fraction
                == (
                    pytest.approx(
                        daily_mpc_input.integration_input.daily_input.initial_soc
                    )
                )
            )
        else:
            previous = result.step_traces[index - 1]
            assert (
                cycle.source_input.physical_cycle_input.battery_state.soc_fraction
                == (
                    pytest.approx(
                        previous.simulation_trace.state.battery_result.next_state.soc
                    )
                )
            )
            assert trace.context.source_context.grid_power_kw == pytest.approx(
                previous.simulation_trace.state.grid_result.actual_grid_power_kw
            )


def test_daily_runner_stops_without_partial_csv_when_cycle_fails(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    _CountingMultiOpportunityCycle.fail_on_call = 3

    with pytest.raises(RuntimeError, match="planned multi-opportunity cycle failure"):
        _runner().run(source)

    assert _CountingMultiOpportunityCycle.calls == 3
    assert _CountingSerializer.calls == 0
    assert _CountingFileExporter.calls == 0
    assert not source.daily_mpc_input.decision_csv_output_path.exists()


def test_contracts_are_frozen_and_runner_owns_no_schedule_logic(tmp_path: Path) -> None:
    source = _source(tmp_path)
    result = _runner().run(source)

    assert result.source_input is source
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, result).csv_content = "changed"

    module_path = (
        Path(__file__).parents[2]
        / "ems_simulator"
        / "multi_opportunity_explainable_mpc_daily.py"
    )
    imported_modules = {
        node.module
        for node in ast.walk(ast.parse(module_path.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom)
    }
    for forbidden in (
        "optimization.multi_opportunity_headroom_schedule",
        "optimization.multi_opportunity_candidate_planning",
        "optimization.multi_opportunity_grid_charge_reservation",
        "optimization.physically_aware_baseline",
    ):
        assert forbidden not in imported_modules
