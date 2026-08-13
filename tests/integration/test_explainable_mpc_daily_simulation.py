"""End-to-end tests for finite explainable daily MPC application execution."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar, cast

import pytest

from capability import (
    ActiveCapabilityCollection,
    AvailableCapabilityCollection,
    CapabilityDescriptor,
    CapabilityMatch,
    CapabilityMatchCollection,
    RequiredCapabilityCollection,
)
from ems_simulator import (
    BatteryParameters,
    EMSIntegrationScenarioInput,
    ExplainableMPCDailySimulationInput,
    ExplainableMPCDailySimulationResult,
    ExplainableMPCDailySimulationRunner,
)
from ems_simulator.input import DailySimulationScenarioInput
from ems_strategy import (
    ActuationHandoffBoundary,
    ActuationHandoffResult,
    DecisionProvenance,
    DeterministicExplainableMPCDecisionCSVFileExporter,
    DeterministicExplainableMPCDecisionCSVRowMapper,
    DeterministicExplainableMPCDecisionCSVSerializer,
    DeterministicExplainableMPCDecisionJournalRecordBuilder,
    DeterministicMPCDecisionExplanationBuilder,
    DeterministicMPCDecisionExplanationFormatter,
    EMSDecision,
    EMSStrategyDescriptor,
    ExplainableMPCDecisionCSVFileExporterBoundary,
    ExplainableMPCDecisionCSVFileExportInput,
    ExplainableMPCDecisionCSVFileExportResult,
    ExplainableMPCDecisionCSVRow,
    ExplainableMPCDecisionCSVRowMappingBoundary,
    ExplainableMPCDecisionCSVRowMappingInput,
    ExplainableMPCDecisionCSVSerializerBoundary,
    ExplainableMPCDecisionJournalRecord,
    ExplainableMPCDecisionJournalRecordBoundary,
    ExplainableMPCDecisionJournalRecordInput,
    FeasibilityBoundary,
    FeasibleDecision,
    FirstStepMPCCurrentActionExtractor,
    FormattedMPCDecisionExplanation,
    MPCConfiguration,
    MPCDecisionExplanation,
    MPCDecisionExplanationBoundary,
    MPCDecisionExplanationFormatInput,
    MPCDecisionExplanationFormatterBoundary,
    MPCDecisionExplanationInput,
    MPCDecisionTranslationBoundary,
    MPCDecisionTranslationInput,
    PhysicallyAwareMPCCycleBoundary,
    PhysicallyAwareMPCCycleInput,
    PhysicallyAwareMPCCycleResult,
    PhysicallyAwareSingleMPCCycleOrchestrator,
)
from forecast import ForecastHorizon, ForecastPoint
from kernel.decision import DecisionIntent as SimulatorDecisionIntent
from kernel.decision import FeasibleDecisionIntent
from objective import ObjectiveCapabilityActivationComposition, ObjectiveDescriptor
from optimization import (
    BatteryOptimizationModel,
    DeterministicBatteryHorizonConstraintAggregator,
    DeterministicBatteryPowerHorizonConstraintEvaluator,
    DeterministicBatterySOCHorizonConstraintEvaluator,
    DeterministicBatterySOCHorizonProjector,
    OptimizationObjective,
    OptimizationObjectiveCollection,
    OptimizationSolutionControlPlanBuilder,
    PhysicallyAwarePriceBaselineOptimizer,
    PriceAwareBaselineOptimizationConfiguration,
    PriceAwareBaselineOptimizer,
)
from simulator import BatterySimulationActuation, SimulationStepIdentity


class _DecisionTranslator(MPCDecisionTranslationBoundary):
    __slots__ = ()

    def translate(self, translation: MPCDecisionTranslationInput) -> EMSDecision:
        step = translation.current_action.selected_step
        context = (
            translation.current_action.source_plan.source_result.source_problem.context
        )
        return EMSDecision(
            context,
            translation.source_strategy,
            step.intent,
            step.requested_power_kw,
        )


class _PassThroughFeasibility(FeasibilityBoundary):
    __slots__ = ()
    calls: ClassVar[int] = 0

    def evaluate(
        self,
        decision: EMSDecision,
        *,
        provenance: DecisionProvenance,
    ) -> FeasibleDecision:
        self.__class__.calls += 1
        return FeasibleDecision(
            decision,
            provenance,
            decision.intent,
            decision.requested_power_kw,
        )


class _SimulationHandoff(ActuationHandoffBoundary):
    __slots__ = ()
    calls: ClassVar[int] = 0

    def _handoff(self, feasible_decision: FeasibleDecision) -> ActuationHandoffResult:
        self.__class__.calls += 1
        magnitude = feasible_decision.approved_power_kw
        signed_power_kw = (
            magnitude
            if feasible_decision.approved_intent.action == "charge"
            else -magnitude
            if feasible_decision.approved_intent.action == "discharge"
            else 0.0
        )
        return ActuationHandoffResult(
            feasible_decision,
            BatterySimulationActuation(
                FeasibleDecisionIntent(SimulatorDecisionIntent(signed_power_kw)),
                signed_power_kw,
            ),
        )


class _CountingMPCCycle(PhysicallyAwareMPCCycleBoundary):
    __slots__ = ("_delegate",)
    calls: ClassVar[int] = 0

    def __init__(self, delegate: PhysicallyAwareMPCCycleBoundary) -> None:
        self._delegate = delegate

    def run_cycle(
        self, cycle_input: PhysicallyAwareMPCCycleInput
    ) -> PhysicallyAwareMPCCycleResult:
        self.__class__.calls += 1
        return self._delegate.run_cycle(cycle_input)


class _FailOnThirdMPCCycle(PhysicallyAwareMPCCycleBoundary):
    __slots__ = ("_delegate",)
    calls: ClassVar[int] = 0

    def __init__(self, delegate: PhysicallyAwareMPCCycleBoundary) -> None:
        self._delegate = delegate

    def run_cycle(
        self, cycle_input: PhysicallyAwareMPCCycleInput
    ) -> PhysicallyAwareMPCCycleResult:
        self.__class__.calls += 1
        if self.__class__.calls == 3:
            raise RuntimeError("planned MPC failure")
        return self._delegate.run_cycle(cycle_input)


class _CountingExplanationBuilder(MPCDecisionExplanationBoundary):
    __slots__ = ()
    calls: ClassVar[int] = 0

    def explain(
        self, explanation_input: MPCDecisionExplanationInput
    ) -> MPCDecisionExplanation:
        self.__class__.calls += 1
        return DeterministicMPCDecisionExplanationBuilder().explain(explanation_input)


class _CountingFormatter(MPCDecisionExplanationFormatterBoundary):
    __slots__ = ()
    calls: ClassVar[int] = 0

    def format(
        self, format_input: MPCDecisionExplanationFormatInput
    ) -> FormattedMPCDecisionExplanation:
        self.__class__.calls += 1
        return DeterministicMPCDecisionExplanationFormatter().format(format_input)


class _CountingJournalBuilder(ExplainableMPCDecisionJournalRecordBoundary):
    __slots__ = ()
    calls: ClassVar[int] = 0

    def build(
        self, record_input: ExplainableMPCDecisionJournalRecordInput
    ) -> ExplainableMPCDecisionJournalRecord:
        self.__class__.calls += 1
        return DeterministicExplainableMPCDecisionJournalRecordBuilder().build(
            record_input
        )


class _CountingRowMapper(ExplainableMPCDecisionCSVRowMappingBoundary):
    __slots__ = ()
    calls: ClassVar[int] = 0

    def map(
        self, mapping_input: ExplainableMPCDecisionCSVRowMappingInput
    ) -> ExplainableMPCDecisionCSVRow:
        self.__class__.calls += 1
        return DeterministicExplainableMPCDecisionCSVRowMapper().map(mapping_input)


class _CountingSerializer(ExplainableMPCDecisionCSVSerializerBoundary):
    __slots__ = ()
    calls: ClassVar[int] = 0

    def serialize(self, rows: tuple[ExplainableMPCDecisionCSVRow, ...]) -> str:
        self.__class__.calls += 1
        return DeterministicExplainableMPCDecisionCSVSerializer().serialize(rows)


class _CountingFileExporter(ExplainableMPCDecisionCSVFileExporterBoundary):
    __slots__ = ()
    calls: ClassVar[int] = 0

    def export(
        self, export_input: ExplainableMPCDecisionCSVFileExportInput
    ) -> ExplainableMPCDecisionCSVFileExportResult:
        self.__class__.calls += 1
        return DeterministicExplainableMPCDecisionCSVFileExporter().export(export_input)


@pytest.fixture(autouse=True)
def _reset_counts() -> None:
    for dependency in (
        _PassThroughFeasibility,
        _SimulationHandoff,
        _CountingMPCCycle,
        _FailOnThirdMPCCycle,
        _CountingExplanationBuilder,
        _CountingFormatter,
        _CountingJournalBuilder,
        _CountingRowMapper,
        _CountingSerializer,
        _CountingFileExporter,
    ):
        dependency.calls = 0


def _daily_input() -> DailySimulationScenarioInput:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return DailySimulationScenarioInput(
        tuple(
            SimulationStepIdentity(index, 3600.0, start + timedelta(hours=index))
            for index in range(24)
        ),
        (0.0,) * 24,
        (1.0,) * 24,
        tuple(0.2 if index % 2 == 0 else 0.9 for index in range(24)),
        BatteryParameters(10.0, 3.0, 3.0, 1.0, 1.0, 0.2),
        0.5,
    )


def _integration_input() -> EMSIntegrationScenarioInput:
    descriptor = CapabilityDescriptor("mpc", "MPC capability.")
    matches = CapabilityMatchCollection(
        RequiredCapabilityCollection((descriptor,)),
        AvailableCapabilityCollection((descriptor,)),
        (CapabilityMatch(descriptor, descriptor),),
        (),
    )
    active = ActiveCapabilityCollection(matches, (descriptor,), ())
    composition = ObjectiveCapabilityActivationComposition(
        ObjectiveDescriptor("energy_cost", "Minimize cost."), active
    )
    return EMSIntegrationScenarioInput(
        _daily_input(), composition, descriptor, 3.0, 5.0, 0.0
    )


def _runner() -> ExplainableMPCDailySimulationRunner:
    return _runner_with_cycle(_CountingMPCCycle(_physical_cycle()))


def _physical_cycle() -> PhysicallyAwareSingleMPCCycleOrchestrator:
    optimizer = PhysicallyAwarePriceBaselineOptimizer(
        PriceAwareBaselineOptimizer(
            PriceAwareBaselineOptimizationConfiguration(0.3, 0.8, 4.0)
        ),
        DeterministicBatterySOCHorizonProjector(),
        DeterministicBatterySOCHorizonConstraintEvaluator(),
        DeterministicBatteryPowerHorizonConstraintEvaluator(),
        DeterministicBatteryHorizonConstraintAggregator(),
    )
    return PhysicallyAwareSingleMPCCycleOrchestrator(
        optimizer,
        OptimizationSolutionControlPlanBuilder(),
        FirstStepMPCCurrentActionExtractor(),
        _DecisionTranslator(),
    )


def _runner_with_cycle(
    cycle: PhysicallyAwareMPCCycleBoundary,
) -> ExplainableMPCDailySimulationRunner:
    return ExplainableMPCDailySimulationRunner(
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


def _source_input(output_path: Path) -> ExplainableMPCDailySimulationInput:
    integration = _integration_input()
    daily = integration.daily_input
    horizons = tuple(
        ForecastHorizon(
            (
                ForecastPoint(
                    _timestamp(step),
                    0.0,
                    1.0,
                    daily.tariff_curve_cny_per_kwh[index],
                ),
            )
        )
        for index, step in enumerate(daily.step_identities)
    )
    return ExplainableMPCDailySimulationInput(
        integration,
        horizons,
        MPCConfiguration(1, 3600.0),
        OptimizationObjectiveCollection(
            (OptimizationObjective("energy_cost", "minimize"),)
        ),
        EMSStrategyDescriptor("mpc", "1.0"),
        BatteryOptimizationModel(10.0, 0.2, 1.0, 3.0, 3.0, 1.0, 1.0),
        "zh-CN",
        output_path,
    )


def _timestamp(step: SimulationStepIdentity) -> datetime:
    if step.timestamp is None:
        raise AssertionError("daily step timestamp must be present")
    return step.timestamp


def test_daily_runner_integrates_exactly_once_and_writes_final_csv(
    tmp_path: Path,
) -> None:
    source = _source_input(tmp_path / "mpc_decisions.csv")
    result = _runner().run(source)

    assert isinstance(result, ExplainableMPCDailySimulationResult)
    assert (
        len(result.step_traces)
        == len(result.journal_records)
        == len(result.csv_rows)
        == 24
    )
    assert (_CountingMPCCycle.calls, _CountingExplanationBuilder.calls) == (24, 24)
    assert (_CountingFormatter.calls, _CountingJournalBuilder.calls) == (24, 24)
    assert (_CountingRowMapper.calls, _PassThroughFeasibility.calls) == (24, 24)
    assert (
        _SimulationHandoff.calls,
        _CountingSerializer.calls,
        _CountingFileExporter.calls,
    ) == (24, 1, 1)
    assert (
        source.decision_csv_output_path.read_text(encoding="utf-8")
        == result.csv_content
    )
    assert len(result.csv_content.splitlines()) >= 25
    assert result.csv_file_result.output_path is source.decision_csv_output_path
    assert [row.timestamp for row in result.csv_rows] == [
        _timestamp(step).isoformat()
        for step in source.integration_input.daily_input.step_identities
    ]
    assert {row.final_action for row in result.csv_rows} == {"charge", "discharge"}
    assert "功率" in result.csv_content
    assert any(row.revision_applied for row in result.csv_rows)
    assert all(row.final_battery_horizon_feasible for row in result.csv_rows)


def test_daily_runner_preserves_planning_and_actual_state_provenance(
    tmp_path: Path,
) -> None:
    source = _source_input(tmp_path / "mpc_decisions.csv")
    result = _runner().run(source)

    for index, trace in enumerate(result.step_traces):
        assert trace.forecast_horizon is source.forecast_horizons[index]
        assert trace.context is trace.mpc_cycle_result.source_input.cycle_input.context
        assert trace.journal_record is result.journal_records[index]
        assert trace.csv_row is result.csv_rows[index]
        assert trace.simulation_trace is result.simulation_result.traces[index]
        assert (
            trace.feasible_decision.source_decision is trace.mpc_cycle_result.decision
        )
        assert trace.handoff.source_feasible_decision is trace.feasible_decision
        if index:
            previous = result.step_traces[index - 1]
            assert (
                trace.mpc_cycle_result.source_input.battery_state.soc_fraction
                == previous.simulation_trace.state.battery_result.next_state.soc
            )
            assert trace.context.source_context.grid_power_kw == pytest.approx(
                previous.simulation_trace.state.grid_result.actual_grid_power_kw
            )


def test_daily_contract_is_frozen_slotted_and_rejects_horizon_misalignment(
    tmp_path: Path,
) -> None:
    source = _source_input(tmp_path / "mpc_decisions.csv")
    assert not hasattr(source, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, source).forecast_horizons = ()
    with pytest.raises(ValueError, match="align"):
        ExplainableMPCDailySimulationInput(
            source.integration_input,
            (
                ForecastHorizon(
                    (ForecastPoint(datetime(2026, 2, 1, tzinfo=UTC), 0.0, 1.0),)
                ),
                *source.forecast_horizons[1:],
            ),
            source.mpc_configuration,
            source.optimization_objectives,
            source.source_strategy,
            source.battery_optimization_model,
            source.explanation_locale,
            source.decision_csv_output_path,
        )


def test_daily_runner_stops_before_csv_serialization_when_an_hour_fails(
    tmp_path: Path,
) -> None:
    source = _source_input(tmp_path / "mpc_decisions.csv")
    runner = _runner_with_cycle(_FailOnThirdMPCCycle(_physical_cycle()))

    with pytest.raises(RuntimeError, match="planned MPC failure"):
        runner.run(source)

    assert _FailOnThirdMPCCycle.calls == 3
    assert _CountingSerializer.calls == 0
    assert _CountingFileExporter.calls == 0
    assert not source.decision_csv_output_path.exists()
