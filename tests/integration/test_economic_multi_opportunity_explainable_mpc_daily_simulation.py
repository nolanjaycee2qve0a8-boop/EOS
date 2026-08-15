"""Integration tests for TASK-160 economic schedule-aware daily simulation."""

import ast
import inspect
from abc import ABC
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from pathlib import Path
from typing import Any, ClassVar, cast, get_type_hints

import pytest

import ems_simulator
from ems_simulator import (
    EconomicMultiOpportunityExplainableMPCDailySimulationBoundary,
    EconomicMultiOpportunityExplainableMPCDailySimulationResult,
    EconomicMultiOpportunityExplainableMPCDailySimulationRunner,
    MultiOpportunityExplainableMPCDailySimulationInput,
)
from ems_simulator.explainable_mpc_daily import ExplainableMPCDailySimulationInput
from ems_strategy import (
    EconomicMultiOpportunityMPCCycleBoundary,
    EconomicMultiOpportunityMPCCycleInput,
    EconomicMultiOpportunityMPCCycleResult,
    EconomicMultiOpportunitySingleMPCCycleOrchestrator,
    FirstStepMPCCurrentActionExtractor,
    MPCConfiguration,
)
from forecast import ForecastHorizon, ForecastPoint
from optimization import (
    DeterministicBatteryHorizonConstraintAggregator,
    DeterministicBatteryPowerHorizonConstraintEvaluator,
    DeterministicBatterySOCHorizonConstraintEvaluator,
    DeterministicBatterySOCHorizonProjector,
    DeterministicEconomicGridChargeValueCalculator,
    DeterministicEconomicMultiOpportunityCandidatePlanner,
    DeterministicEconomicMultiOpportunityPhysicalOptimizer,
    DeterministicEconomicPlanningCalculator,
    DeterministicExplicitCandidatePhysicalReviser,
    DeterministicMultiOpportunityGridChargeReservationCalculator,
    DeterministicMultiOpportunityHeadroomScheduleCalculator,
    DeterministicPVHeadroomRequirementCalculator,
    DeterministicPVOpportunitySequenceCalculator,
    EconomicMultiOpportunityPhysicalOptimizationBoundary,
    NetLoadAwareBaselineOptimizationConfiguration,
    NetLoadAwareBaselineOptimizer,
    OptimizationObjective,
    OptimizationObjectiveCollection,
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
    _timestamp,
)

POSITIVE_CONFIGURATION = NetLoadAwareBaselineOptimizationConfiguration(0.3, 0.8, 3.0)
NEGATIVE_CONFIGURATION = NetLoadAwareBaselineOptimizationConfiguration(0.8, 1.0, 3.0)
OPPORTUNITY_CONFIGURATION = PVOpportunityWindowConfiguration(0)


class _CountingEconomicCycle(EconomicMultiOpportunityMPCCycleBoundary):
    __slots__ = ("delegate",)

    calls: ClassVar[int] = 0
    fail_on_call: ClassVar[int | None] = None
    delegate: EconomicMultiOpportunityMPCCycleBoundary

    def __init__(self, delegate: EconomicMultiOpportunityMPCCycleBoundary) -> None:
        self.delegate = delegate

    def run_cycle(
        self,
        cycle_input: EconomicMultiOpportunityMPCCycleInput,
    ) -> EconomicMultiOpportunityMPCCycleResult:
        self.__class__.calls += 1
        if self.__class__.fail_on_call == self.__class__.calls:
            raise RuntimeError("planned economic MPC cycle failure")
        return self.delegate.run_cycle(cycle_input)


@pytest.fixture(autouse=True)
def _reset_counts() -> None:
    _CountingEconomicCycle.calls = 0
    _CountingEconomicCycle.fail_on_call = None
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


def _economic_cycle(
    configuration: NetLoadAwareBaselineOptimizationConfiguration,
) -> EconomicMultiOpportunitySingleMPCCycleOrchestrator:
    optimization: EconomicMultiOpportunityPhysicalOptimizationBoundary = (
        DeterministicEconomicMultiOpportunityPhysicalOptimizer(
            DeterministicMultiOpportunityHeadroomScheduleCalculator(
                DeterministicPVOpportunitySequenceCalculator(),
                DeterministicPVHeadroomRequirementCalculator(),
            ),
            DeterministicEconomicPlanningCalculator(),
            DeterministicEconomicMultiOpportunityCandidatePlanner(
                NetLoadAwareBaselineOptimizer(configuration),
                DeterministicMultiOpportunityGridChargeReservationCalculator(),
                DeterministicEconomicGridChargeValueCalculator(),
            ),
            DeterministicExplicitCandidatePhysicalReviser(
                DeterministicBatterySOCHorizonProjector(),
                DeterministicBatterySOCHorizonConstraintEvaluator(),
                DeterministicBatteryPowerHorizonConstraintEvaluator(),
                DeterministicBatteryHorizonConstraintAggregator(),
            ),
        )
    )
    return EconomicMultiOpportunitySingleMPCCycleOrchestrator(
        optimization,
        OptimizationSolutionControlPlanBuilder(),
        FirstStepMPCCurrentActionExtractor(),
        _DecisionTranslator(),
    )


def _runner(
    configuration: NetLoadAwareBaselineOptimizationConfiguration,
    cycle: EconomicMultiOpportunityMPCCycleBoundary | None = None,
) -> EconomicMultiOpportunityExplainableMPCDailySimulationRunner:
    return EconomicMultiOpportunityExplainableMPCDailySimulationRunner(
        cycle or _CountingEconomicCycle(_economic_cycle(configuration)),
        _CountingExplanationBuilder(),
        _CountingFormatter(),
        _CountingJournalBuilder(),
        _CountingRowMapper(),
        _CountingSerializer(),
        _CountingFileExporter(),
        _PassThroughFeasibility(),
        _SimulationHandoff(),
    )


def _source(
    output_path: Path,
    configuration: NetLoadAwareBaselineOptimizationConfiguration,
    *,
    current_price: float,
    future_price: float,
    current_pv_kw: float = 0.0,
) -> MultiOpportunityExplainableMPCDailySimulationInput:
    base = _source_input(output_path)
    base_daily = base.integration_input.daily_input
    daily = replace(
        base_daily,
        pv_power_curve_kw=(current_pv_kw, *base_daily.pv_power_curve_kw[1:]),
    )
    integration = replace(base.integration_input, daily_input=daily)
    horizons = tuple(
        ForecastHorizon(
            (
                ForecastPoint(
                    _timestamp(step),
                    current_pv_kw if index == 0 else 0.0,
                    1.0,
                    current_price,
                ),
                ForecastPoint(
                    _timestamp(step) + timedelta(hours=1),
                    0.0,
                    1.0,
                    future_price,
                ),
            )
        )
        for index, step in enumerate(daily.step_identities)
    )
    daily_mpc_input = ExplainableMPCDailySimulationInput(
        integration,
        horizons,
        MPCConfiguration(2, 3600.0),
        OptimizationObjectiveCollection(
            (OptimizationObjective("energy_cost", "minimize"),)
        ),
        base.source_strategy,
        base.battery_optimization_model,
        base.explanation_locale,
        output_path,
    )
    return MultiOpportunityExplainableMPCDailySimulationInput(
        daily_mpc_input,
        configuration,
        OPPORTUNITY_CONFIGURATION,
    )


def test_daily_runner_retains_outer_provenance_and_actual_feedback(
    tmp_path: Path,
) -> None:
    source = _source(
        tmp_path / "economic_decisions.csv",
        POSITIVE_CONFIGURATION,
        current_price=0.2,
        future_price=0.9,
    )
    result = _runner(POSITIVE_CONFIGURATION).run(source)
    daily_mpc = source.daily_mpc_input

    assert isinstance(
        result,
        EconomicMultiOpportunityExplainableMPCDailySimulationResult,
    )
    assert (
        len(result.step_traces)
        == len(result.journal_records)
        == len(result.csv_rows)
        == 24
    )
    assert _CountingEconomicCycle.calls == 24
    assert (
        _CountingExplanationBuilder.calls,
        _CountingFormatter.calls,
        _CountingJournalBuilder.calls,
        _CountingRowMapper.calls,
        _PassThroughFeasibility.calls,
        _SimulationHandoff.calls,
    ) == (24, 24, 24, 24, 24, 24)
    assert (_CountingSerializer.calls, _CountingFileExporter.calls) == (1, 1)

    for index, trace in enumerate(result.step_traces):
        cycle = trace.economic_multi_opportunity_mpc_cycle_result
        output = cycle.economic_multi_opportunity_optimization_output
        assert trace.forecast_horizon is daily_mpc.forecast_horizons[index]
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
            output.economic_planning_evidence.source_input.forecast_horizon
            is trace.forecast_horizon
        )
        assert (
            output.physical_output.candidate_output
            is output.candidate_planning_result.final_output
        )
        if index == 0:
            assert (
                cycle.source_input.physical_cycle_input.battery_state.soc_fraction
                == pytest.approx(daily_mpc.integration_input.daily_input.initial_soc)
            )
        else:
            previous = result.step_traces[index - 1]
            assert (
                cycle.source_input.physical_cycle_input.battery_state.soc_fraction
                == pytest.approx(
                    previous.simulation_trace.state.battery_result.next_state.soc
                )
            )
            assert trace.context.source_context.grid_power_kw == pytest.approx(
                previous.simulation_trace.state.grid_result.actual_grid_power_kw
            )


def test_negative_economics_suppresses_grid_charge_through_simulation(
    tmp_path: Path,
) -> None:
    source = _source(
        tmp_path / "negative_economic_decisions.csv",
        NEGATIVE_CONFIGURATION,
        current_price=0.8,
        future_price=0.79,
    )
    result = _runner(NEGATIVE_CONFIGURATION).run(source)
    trace = result.step_traces[0]
    cycle = trace.economic_multi_opportunity_mpc_cycle_result
    output = cycle.economic_multi_opportunity_optimization_output

    assert output.candidate_planning_result.economic_value_result is not None
    assert (
        output.candidate_planning_result.economic_value_result.economic_classification
        == "negative"
    )
    assert cycle.decision.intent.action == "idle"
    assert trace.handoff.actuation.battery_power_kw == 0.0
    assert trace.simulation_trace.state.battery_result.next_state.soc == pytest.approx(
        source.daily_mpc_input.integration_input.daily_input.initial_soc
    )


def test_pv_surplus_bypasses_economic_gate_and_executes_physical_charge(
    tmp_path: Path,
) -> None:
    source = _source(
        tmp_path / "pv_surplus_decisions.csv",
        POSITIVE_CONFIGURATION,
        current_price=0.2,
        future_price=0.2,
        current_pv_kw=6.0,
    )
    result = _runner(POSITIVE_CONFIGURATION).run(source)
    trace = result.step_traces[0]
    cycle = trace.economic_multi_opportunity_mpc_cycle_result
    output = cycle.economic_multi_opportunity_optimization_output

    assert output.candidate_planning_result.reservation_result is None
    assert output.candidate_planning_result.economic_value_result is None
    assert trace.handoff.actuation.battery_power_kw == pytest.approx(3.0)
    assert trace.simulation_trace.state.battery_result.next_state.soc > 0.5


def test_daily_runner_stops_without_partial_csv_on_cycle_failure(
    tmp_path: Path,
) -> None:
    source = _source(
        tmp_path / "failed_economic_decisions.csv",
        POSITIVE_CONFIGURATION,
        current_price=0.2,
        future_price=0.9,
    )
    _CountingEconomicCycle.fail_on_call = 3

    with pytest.raises(RuntimeError, match="planned economic MPC cycle failure"):
        _runner(POSITIVE_CONFIGURATION).run(source)

    assert _CountingEconomicCycle.calls == 3
    assert _CountingSerializer.calls == 0
    assert _CountingFileExporter.calls == 0
    assert not source.daily_mpc_input.decision_csv_output_path.exists()


def test_contracts_are_immutable_and_runner_has_no_inner_economic_logic() -> None:
    boundary = EconomicMultiOpportunityExplainableMPCDailySimulationBoundary
    assert issubclass(boundary, ABC)
    assert inspect.isabstract(boundary)
    assert boundary.__slots__ == ()
    assert (
        get_type_hints(
            EconomicMultiOpportunityExplainableMPCDailySimulationBoundary.run
        )["return"]
        is EconomicMultiOpportunityExplainableMPCDailySimulationResult
    )

    module_path = (
        Path(ems_simulator.__file__).parent
        / "economic_multi_opportunity_explainable_mpc_daily.py"
    )
    source = module_path.read_text(encoding="utf-8")
    imported_modules = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    }
    for forbidden in (
        "optimization.economic_planning",
        "optimization.economic_grid_charge_value",
        "optimization.economic_multi_opportunity_candidate_planning",
        "optimization.multi_opportunity_headroom_schedule",
        "optimization.multi_opportunity_grid_charge_reservation",
    ):
        assert forbidden not in imported_modules
    assert "DeterministicEconomicMultiOpportunityPhysicalOptimizer" not in source
    for name in (
        "EconomicMultiOpportunityExplainableMPCDailySimulationStepTrace",
        "EconomicMultiOpportunityExplainableMPCDailySimulationResult",
        "EconomicMultiOpportunityExplainableMPCDailySimulationBoundary",
        "EconomicMultiOpportunityExplainableMPCDailySimulationRunner",
    ):
        assert name in ems_simulator.__all__


def test_result_is_frozen_and_slotted(tmp_path: Path) -> None:
    source = _source(
        tmp_path / "immutable_economic_decisions.csv",
        POSITIVE_CONFIGURATION,
        current_price=0.2,
        future_price=0.9,
    )
    result = _runner(POSITIVE_CONFIGURATION).run(source)

    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, result).csv_content = "changed"
