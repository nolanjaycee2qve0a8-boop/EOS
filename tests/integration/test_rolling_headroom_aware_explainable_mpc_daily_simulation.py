"""Integration tests for finite rolling-headroom explainable daily simulation."""

from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, ClassVar, cast

import pytest

from ems_simulator import (
    RollingHeadroomAwareExplainableMPCDailySimulationResult,
    RollingHeadroomAwareExplainableMPCDailySimulationRunner,
)
from ems_strategy import (
    FirstStepMPCCurrentActionExtractor,
    PhysicallyAwareMPCCycleInput,
    RollingHeadroomAwareMPCCycleBoundary,
    RollingHeadroomAwareMPCCycleResult,
    RollingHeadroomAwareSingleMPCCycleOrchestrator,
)
from optimization import (
    DeterministicBatteryHorizonConstraintAggregator,
    DeterministicBatteryPowerHorizonConstraintEvaluator,
    DeterministicBatterySOCHorizonConstraintEvaluator,
    DeterministicBatterySOCHorizonProjector,
    DeterministicExplicitCandidatePhysicalReviser,
    DeterministicHeadroomAwareCandidatePlanner,
    DeterministicHeadroomAwareGridChargeReservationCalculator,
    DeterministicPVHeadroomRequirementCalculator,
    DeterministicPVOpportunityWindowSelector,
    DeterministicRollingHeadroomAwarePhysicalOptimizer,
    DeterministicRollingPVHeadroomRequirementCalculator,
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


class _CountingRollingCycle(RollingHeadroomAwareMPCCycleBoundary):
    __slots__ = ("_delegate",)
    calls: ClassVar[int] = 0
    fail_on_call: ClassVar[int | None] = None

    def __init__(self, delegate: RollingHeadroomAwareMPCCycleBoundary) -> None:
        self._delegate = delegate

    def run_cycle(
        self, cycle_input: PhysicallyAwareMPCCycleInput
    ) -> RollingHeadroomAwareMPCCycleResult:
        self.__class__.calls += 1
        if self.__class__.fail_on_call == self.__class__.calls:
            raise RuntimeError("planned rolling cycle failure")
        return self._delegate.run_cycle(cycle_input)


@pytest.fixture(autouse=True)
def _reset_counts() -> None:
    _CountingRollingCycle.calls = 0
    _CountingRollingCycle.fail_on_call = None
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


def _cycle() -> RollingHeadroomAwareSingleMPCCycleOrchestrator:
    optimization = DeterministicRollingHeadroomAwarePhysicalOptimizer(
        DeterministicRollingPVHeadroomRequirementCalculator(
            DeterministicPVOpportunityWindowSelector(),
            DeterministicPVHeadroomRequirementCalculator(),
        ),
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
        PVOpportunityWindowConfiguration(1),
    )
    return RollingHeadroomAwareSingleMPCCycleOrchestrator(
        optimization,
        OptimizationSolutionControlPlanBuilder(),
        FirstStepMPCCurrentActionExtractor(),
        _DecisionTranslator(),
    )


def _runner(
    cycle: RollingHeadroomAwareMPCCycleBoundary | None = None,
) -> RollingHeadroomAwareExplainableMPCDailySimulationRunner:
    return RollingHeadroomAwareExplainableMPCDailySimulationRunner(
        cycle or _CountingRollingCycle(_cycle()),
        _CountingExplanationBuilder(),
        _CountingFormatter(),
        _CountingJournalBuilder(),
        _CountingRowMapper(),
        _CountingSerializer(),
        _CountingFileExporter(),
        _PassThroughFeasibility(),
        _SimulationHandoff(),
    )


def test_daily_runner_preserves_24_rolling_cycles_actual_feedback_and_provenance(
    tmp_path: Path,
) -> None:
    source = _source_input(tmp_path / "rolling_decisions.csv")
    result = _runner().run(source)

    assert isinstance(result, RollingHeadroomAwareExplainableMPCDailySimulationResult)
    assert (
        len(result.step_traces)
        == len(result.journal_records)
        == len(result.csv_rows)
        == 24
    )
    assert _CountingRollingCycle.calls == 24
    assert (
        _CountingExplanationBuilder.calls,
        _CountingFormatter.calls,
        _CountingJournalBuilder.calls,
        _CountingRowMapper.calls,
        _PassThroughFeasibility.calls,
        _SimulationHandoff.calls,
    ) == (24, 24, 24, 24, 24, 24)
    assert (_CountingSerializer.calls, _CountingFileExporter.calls) == (1, 1)
    assert (
        source.decision_csv_output_path.read_text(encoding="utf-8")
        == result.csv_content
    )

    for index, trace in enumerate(result.step_traces):
        cycle = trace.rolling_headroom_mpc_cycle_result
        rolling = cycle.rolling_headroom_optimization_output
        assert trace.forecast_horizon is source.forecast_horizons[index]
        assert trace.context is cycle.source_input.cycle_input.context
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
        assert rolling.source_input is cycle.physically_aware_input
        assert (
            rolling.rolling_headroom_requirement.source_input.forecast_horizon
            is trace.forecast_horizon
        )
        assert (
            rolling.physical_output.candidate_output
            is rolling.candidate_planning_result.final_output
        )
        if index == 0:
            assert cycle.source_input.battery_state.soc_fraction == pytest.approx(
                source.integration_input.daily_input.initial_soc
            )
        else:
            previous = result.step_traces[index - 1]
            assert cycle.source_input.battery_state.soc_fraction == pytest.approx(
                previous.simulation_trace.state.battery_result.next_state.soc
            )
            assert trace.context.source_context.grid_power_kw == pytest.approx(
                previous.simulation_trace.state.grid_result.actual_grid_power_kw
            )


def test_daily_runner_stops_without_partial_csv_when_rolling_cycle_fails(
    tmp_path: Path,
) -> None:
    source = _source_input(tmp_path / "rolling_decisions.csv")
    _CountingRollingCycle.fail_on_call = 3

    with pytest.raises(RuntimeError, match="planned rolling cycle failure"):
        _runner().run(source)

    assert _CountingRollingCycle.calls == 3
    assert _CountingSerializer.calls == 0
    assert _CountingFileExporter.calls == 0
    assert not source.decision_csv_output_path.exists()


def test_daily_result_contract_is_frozen_and_reuses_exact_input(tmp_path: Path) -> None:
    source = _source_input(tmp_path / "rolling_decisions.csv")
    result = _runner().run(source)

    assert result.source_input is source
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, result).csv_content = "changed"
