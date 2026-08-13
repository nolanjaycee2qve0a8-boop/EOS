"""Integration tests for the finite headroom-aware explainable daily runner."""

from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, ClassVar, cast

import pytest

from ems_simulator import (
    HeadroomAwareExplainableMPCDailySimulationResult,
    HeadroomAwareExplainableMPCDailySimulationRunner,
)
from ems_strategy import (
    FirstStepMPCCurrentActionExtractor,
    HeadroomAwareMPCCycleBoundary,
    HeadroomAwareMPCCycleResult,
    HeadroomAwareSingleMPCCycleOrchestrator,
    PhysicallyAwareMPCCycleInput,
)
from optimization import (
    DeterministicBatteryHorizonConstraintAggregator,
    DeterministicBatteryPowerHorizonConstraintEvaluator,
    DeterministicBatterySOCHorizonConstraintEvaluator,
    DeterministicBatterySOCHorizonProjector,
    DeterministicExplicitCandidatePhysicalReviser,
    DeterministicHeadroomAwareCandidatePlanner,
    DeterministicHeadroomAwareGridChargeReservationCalculator,
    DeterministicHeadroomAwarePhysicalOptimizer,
    DeterministicPVHeadroomRequirementCalculator,
    NetLoadAwareBaselineOptimizationConfiguration,
    NetLoadAwareBaselineOptimizer,
    OptimizationSolutionControlPlanBuilder,
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


class _CountingHeadroomCycle(HeadroomAwareMPCCycleBoundary):
    __slots__ = ("_delegate",)
    calls: ClassVar[int] = 0
    fail_on_call: ClassVar[int | None] = None

    def __init__(self, delegate: HeadroomAwareMPCCycleBoundary) -> None:
        self._delegate = delegate

    def run_cycle(
        self,
        cycle_input: PhysicallyAwareMPCCycleInput,
    ) -> HeadroomAwareMPCCycleResult:
        self.__class__.calls += 1
        if self.__class__.fail_on_call == self.__class__.calls:
            raise RuntimeError("planned headroom cycle failure")
        return self._delegate.run_cycle(cycle_input)


@pytest.fixture(autouse=True)
def _reset_counts() -> None:
    _CountingHeadroomCycle.calls = 0
    _CountingHeadroomCycle.fail_on_call = None
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


def _headroom_cycle() -> HeadroomAwareSingleMPCCycleOrchestrator:
    optimizer = DeterministicHeadroomAwarePhysicalOptimizer(
        DeterministicPVHeadroomRequirementCalculator(),
        DeterministicHeadroomAwareCandidatePlanner(
            NetLoadAwareBaselineOptimizer(
                NetLoadAwareBaselineOptimizationConfiguration(0.3, 0.8, 4.0)
            ),
            DeterministicHeadroomAwareGridChargeReservationCalculator(),
        ),
        DeterministicExplicitCandidatePhysicalReviser(
            DeterministicBatterySOCHorizonProjector(),
            DeterministicBatterySOCHorizonConstraintEvaluator(),
            DeterministicBatteryPowerHorizonConstraintEvaluator(),
            DeterministicBatteryHorizonConstraintAggregator(),
        ),
    )
    return HeadroomAwareSingleMPCCycleOrchestrator(
        optimizer,
        OptimizationSolutionControlPlanBuilder(),
        FirstStepMPCCurrentActionExtractor(),
        _DecisionTranslator(),
    )


def _runner() -> HeadroomAwareExplainableMPCDailySimulationRunner:
    return _runner_with_cycle(_CountingHeadroomCycle(_headroom_cycle()))


def _runner_with_cycle(
    cycle: HeadroomAwareMPCCycleBoundary,
) -> HeadroomAwareExplainableMPCDailySimulationRunner:
    return HeadroomAwareExplainableMPCDailySimulationRunner(
        cycle,
        _CountingExplanationBuilder(),
        _CountingFormatter(),
        _CountingJournalBuilder(),
        _CountingRowMapper(),
        _CountingSerializer(),
        _CountingFileExporter(),
        _PassThroughFeasibility(),
        _SimulationHandoff(),
    )


def test_daily_runner_preserves_24_headroom_cycles_and_actual_state_feedback(
    tmp_path: Path,
) -> None:
    source = _source_input(tmp_path / "headroom_decisions.csv")
    result = _runner().run(source)

    assert isinstance(result, HeadroomAwareExplainableMPCDailySimulationResult)
    assert (
        len(result.step_traces)
        == len(result.journal_records)
        == len(result.csv_rows)
        == 24
    )
    assert _CountingHeadroomCycle.calls == 24
    assert (_CountingExplanationBuilder.calls, _CountingJournalBuilder.calls) == (
        24,
        24,
    )
    assert (_CountingSerializer.calls, _CountingFileExporter.calls) == (1, 1)
    assert (
        source.decision_csv_output_path.read_text(encoding="utf-8")
        == result.csv_content
    )
    assert (
        result.step_traces[
            0
        ].headroom_mpc_cycle_result.source_input.battery_state.soc_fraction
        == pytest.approx(source.integration_input.daily_input.initial_soc)
    )

    for index, trace in enumerate(result.step_traces):
        cycle = trace.headroom_mpc_cycle_result
        assert trace.forecast_horizon is source.forecast_horizons[index]
        assert trace.context is cycle.source_input.cycle_input.context
        assert trace.physical_cycle_view is cycle.physical_cycle_view
        assert cycle.decision is trace.physical_cycle_view.decision
        assert (
            cycle.physical_cycle_view.optimization_output
            is cycle.headroom_optimization_output.physical_output
        )
        assert cycle.control_plan.source_result is (
            cycle.headroom_optimization_output.physical_output.final_output.solution.source_result
        )
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
        if index:
            previous = result.step_traces[index - 1]
            assert cycle.source_input.battery_state.soc_fraction == (
                previous.simulation_trace.state.battery_result.next_state.soc
            )
            assert trace.context.source_context.grid_power_kw == pytest.approx(
                previous.simulation_trace.state.grid_result.actual_grid_power_kw
            )


def test_daily_runner_stops_before_partial_csv_output_on_cycle_failure(
    tmp_path: Path,
) -> None:
    source = _source_input(tmp_path / "headroom_decisions.csv")
    _CountingHeadroomCycle.fail_on_call = 3

    with pytest.raises(RuntimeError, match="planned headroom cycle failure"):
        _runner().run(source)

    assert _CountingHeadroomCycle.calls == 3
    assert _CountingSerializer.calls == 0
    assert _CountingFileExporter.calls == 0
    assert not source.decision_csv_output_path.exists()


def test_daily_result_contract_is_frozen_and_input_is_reused_exactly(
    tmp_path: Path,
) -> None:
    source = _source_input(tmp_path / "headroom_decisions.csv")
    result = _runner().run(source)

    assert result.source_input is source
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, result).csv_content = "changed"
