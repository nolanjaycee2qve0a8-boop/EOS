"""Finite daily integration for TASK-143 rolling-headroom MPC cycles.

This is a parallel application path.  It preserves the frozen TASK-138
full-horizon runner and passes only the exact TASK-143 physical compatibility
view to established physical explanation, journal, and CSV contracts.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ems_simulator.ems_integration import EMSIntegrationRunner
from ems_simulator.explainable_mpc_daily import ExplainableMPCDailySimulationInput
from ems_simulator.input import HOURS_PER_DAY, DailySimulationScenarioInput
from ems_simulator.runner import DailySimulationResult
from ems_strategy import (
    ActuationHandoffBoundary,
    ActuationHandoffResult,
    DecisionProvenance,
    EMSContext,
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
    FormattedMPCDecisionExplanation,
    MPCCycleInput,
    MPCDecisionExplanation,
    MPCDecisionExplanationBoundary,
    MPCDecisionExplanationFormatInput,
    MPCDecisionExplanationFormatterBoundary,
    MPCDecisionExplanationInput,
    PhysicallyAwareMPCCycleInput,
    PhysicallyAwareMPCCycleResult,
    RollingHeadroomAwareMPCCycleBoundary,
    RollingHeadroomAwareMPCCycleResult,
)
from forecast import ForecastHorizon
from optimization import BatteryOptimizationState
from simulator import (
    BatterySimulationState,
    SimulationExecutionTrace,
    SimulationScenario,
    SimulationStepInput,
    SimulationStepProgression,
)


@dataclass(frozen=True, slots=True)
class RollingHeadroomAwareExplainableMPCDailySimulationStepTrace:
    """Retain one outer rolling cycle and its exact physical compatibility view."""

    context: EMSContext
    forecast_horizon: ForecastHorizon
    rolling_headroom_mpc_cycle_result: RollingHeadroomAwareMPCCycleResult
    physical_cycle_view: PhysicallyAwareMPCCycleResult
    explanation: MPCDecisionExplanation
    formatted_explanation: FormattedMPCDecisionExplanation
    journal_record: ExplainableMPCDecisionJournalRecord
    csv_row: ExplainableMPCDecisionCSVRow
    decision_provenance: DecisionProvenance
    feasible_decision: FeasibleDecision
    handoff: ActuationHandoffResult
    simulation_trace: SimulationExecutionTrace

    def __post_init__(self) -> None:
        for field_name, expected_type in (
            ("context", EMSContext),
            ("forecast_horizon", ForecastHorizon),
            ("rolling_headroom_mpc_cycle_result", RollingHeadroomAwareMPCCycleResult),
            ("physical_cycle_view", PhysicallyAwareMPCCycleResult),
            ("explanation", MPCDecisionExplanation),
            ("formatted_explanation", FormattedMPCDecisionExplanation),
            ("journal_record", ExplainableMPCDecisionJournalRecord),
            ("csv_row", ExplainableMPCDecisionCSVRow),
            ("decision_provenance", DecisionProvenance),
            ("feasible_decision", FeasibleDecision),
            ("handoff", ActuationHandoffResult),
            ("simulation_trace", SimulationExecutionTrace),
        ):
            if not isinstance(getattr(self, field_name), expected_type):
                raise TypeError(f"{field_name} must be a {expected_type.__name__}")

        cycle = self.rolling_headroom_mpc_cycle_result
        view = self.physical_cycle_view
        if cycle.source_input.cycle_input.context is not self.context:
            raise ValueError("rolling MPC cycle must preserve exact context identity")
        if cycle.source_input.cycle_input.forecast_horizon is not self.forecast_horizon:
            raise ValueError("rolling MPC cycle must preserve exact forecast identity")
        if view is not cycle.physical_cycle_view:
            raise ValueError(
                "physical_cycle_view must be the exact cycle compatibility view"
            )
        if cycle.decision is not view.decision:
            raise ValueError("rolling and physical views must preserve exact decision")
        if self.explanation.source_input.cycle_result is not view:
            raise ValueError("explanation must preserve exact physical cycle view")
        if self.formatted_explanation.source_input.explanation is not self.explanation:
            raise ValueError("formatted explanation must preserve exact explanation")
        record_input = self.journal_record.source_input
        if record_input.cycle_result is not view:
            raise ValueError("journal record must preserve exact physical cycle view")
        if record_input.explanation is not self.explanation:
            raise ValueError("journal record must preserve exact explanation")
        if record_input.formatted_explanation is not self.formatted_explanation:
            raise ValueError("journal record must preserve exact formatted explanation")
        if self.decision_provenance.decision is not cycle.decision:
            raise ValueError("provenance must preserve exact rolling decision")
        if self.feasible_decision.source_decision is not cycle.decision:
            raise ValueError("feasible decision must preserve exact rolling decision")
        if self.feasible_decision.source_provenance is not self.decision_provenance:
            raise ValueError("feasible decision must preserve exact provenance")
        if self.handoff.source_feasible_decision is not self.feasible_decision:
            raise ValueError("handoff must preserve exact feasible decision")
        if (
            self.simulation_trace.simulation_input.battery_input.actuation
            is not self.handoff.actuation
        ):
            raise ValueError("simulation trace must preserve exact handoff actuation")


@dataclass(frozen=True, slots=True)
class RollingHeadroomAwareExplainableMPCDailySimulationResult:
    """Retain all completed daily evidence and the one final CSV write effect."""

    source_input: ExplainableMPCDailySimulationInput
    simulation_result: DailySimulationResult
    step_traces: tuple[RollingHeadroomAwareExplainableMPCDailySimulationStepTrace, ...]
    journal_records: tuple[ExplainableMPCDecisionJournalRecord, ...]
    csv_rows: tuple[ExplainableMPCDecisionCSVRow, ...]
    csv_content: str
    csv_file_result: ExplainableMPCDecisionCSVFileExportResult

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, ExplainableMPCDailySimulationInput):
            raise TypeError(
                "source_input must be an ExplainableMPCDailySimulationInput"
            )
        if not isinstance(self.simulation_result, DailySimulationResult):
            raise TypeError("simulation_result must be a DailySimulationResult")
        for field_name, values, item_type in (
            (
                "step_traces",
                self.step_traces,
                RollingHeadroomAwareExplainableMPCDailySimulationStepTrace,
            ),
            (
                "journal_records",
                self.journal_records,
                ExplainableMPCDecisionJournalRecord,
            ),
            ("csv_rows", self.csv_rows, ExplainableMPCDecisionCSVRow),
        ):
            if not isinstance(values, tuple):
                raise TypeError(f"{field_name} must be a tuple")
            if len(values) != HOURS_PER_DAY:
                raise ValueError(f"{field_name} must contain exactly 24 values")
            if any(not isinstance(value, item_type) for value in values):
                raise TypeError(f"{field_name} contains invalid items")
        if not isinstance(self.csv_content, str):
            raise TypeError("csv_content must be a str")
        if not isinstance(
            self.csv_file_result, ExplainableMPCDecisionCSVFileExportResult
        ):
            raise TypeError(
                "csv_file_result must be an ExplainableMPCDecisionCSVFileExportResult"
            )
        if (
            self.simulation_result.source_input
            is not self.source_input.integration_input.daily_input
        ):
            raise ValueError("simulation result must preserve exact daily input")
        for index, trace in enumerate(self.step_traces):
            if trace.journal_record is not self.journal_records[index]:
                raise ValueError("trace must preserve exact journal record")
            if trace.csv_row is not self.csv_rows[index]:
                raise ValueError("trace must preserve exact CSV row")
            if trace.simulation_trace is not self.simulation_result.traces[index]:
                raise ValueError("trace must preserve exact simulation trace")
        file_input = self.csv_file_result.source_input
        if file_input.csv_content != self.csv_content:
            raise ValueError("CSV file result must preserve exact CSV content")
        if file_input.output_path is not self.source_input.decision_csv_output_path:
            raise ValueError("CSV file result must preserve exact output path")


class RollingHeadroomAwareExplainableMPCDailySimulationBoundary(ABC):
    """Define one finite caller-requested 24-step rolling-headroom simulation."""

    __slots__ = ()

    @abstractmethod
    def run(
        self, source_input: ExplainableMPCDailySimulationInput
    ) -> RollingHeadroomAwareExplainableMPCDailySimulationResult:
        """Run the explicit day without scheduling or hidden repetition."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class RollingHeadroomAwareExplainableMPCDailySimulationRunner(
    RollingHeadroomAwareExplainableMPCDailySimulationBoundary
):
    """Compose 24 caller-owned TASK-143 cycles with actual simulator feedback."""

    mpc_cycle_boundary: RollingHeadroomAwareMPCCycleBoundary
    explanation_builder: MPCDecisionExplanationBoundary
    explanation_formatter: MPCDecisionExplanationFormatterBoundary
    journal_record_builder: ExplainableMPCDecisionJournalRecordBoundary
    csv_row_mapper: ExplainableMPCDecisionCSVRowMappingBoundary
    csv_serializer: ExplainableMPCDecisionCSVSerializerBoundary
    csv_file_exporter: ExplainableMPCDecisionCSVFileExporterBoundary
    feasibility: FeasibilityBoundary
    handoff: ActuationHandoffBoundary

    def __post_init__(self) -> None:
        for field_name, expected_type in (
            ("mpc_cycle_boundary", RollingHeadroomAwareMPCCycleBoundary),
            ("explanation_builder", MPCDecisionExplanationBoundary),
            ("explanation_formatter", MPCDecisionExplanationFormatterBoundary),
            ("journal_record_builder", ExplainableMPCDecisionJournalRecordBoundary),
            ("csv_row_mapper", ExplainableMPCDecisionCSVRowMappingBoundary),
            ("csv_serializer", ExplainableMPCDecisionCSVSerializerBoundary),
            ("csv_file_exporter", ExplainableMPCDecisionCSVFileExporterBoundary),
            ("feasibility", FeasibilityBoundary),
            ("handoff", ActuationHandoffBoundary),
        ):
            if not isinstance(getattr(self, field_name), expected_type):
                raise TypeError(f"{field_name} must be a {expected_type.__name__}")

    def run(
        self, source_input: ExplainableMPCDailySimulationInput
    ) -> RollingHeadroomAwareExplainableMPCDailySimulationResult:
        if not isinstance(source_input, ExplainableMPCDailySimulationInput):
            raise TypeError(
                "source_input must be an ExplainableMPCDailySimulationInput"
            )
        integration = source_input.integration_input
        daily_input = integration.daily_input
        battery_state = BatterySimulationState(daily_input.initial_soc)
        previous_grid_power_kw = integration.initial_grid_power_kw
        steps: list[SimulationStepInput] = []
        simulation_traces: list[SimulationExecutionTrace] = []
        progressions: list[SimulationStepProgression] = []
        daily_traces: list[
            RollingHeadroomAwareExplainableMPCDailySimulationStepTrace
        ] = []
        records: list[ExplainableMPCDecisionJournalRecord] = []
        rows: list[ExplainableMPCDecisionCSVRow] = []

        for index in range(HOURS_PER_DAY):
            context = EMSIntegrationRunner._create_context(
                integration, index, battery_state, previous_grid_power_kw
            )
            horizon = source_input.forecast_horizons[index]
            cycle_input = PhysicallyAwareMPCCycleInput(
                MPCCycleInput(
                    context,
                    horizon,
                    source_input.mpc_configuration,
                    source_input.optimization_objectives,
                    source_input.source_strategy,
                ),
                BatteryOptimizationState(battery_state.soc),
                source_input.battery_optimization_model,
            )
            cycle = self.mpc_cycle_boundary.run_cycle(cycle_input)
            self._require_cycle(cycle, cycle_input)
            view = cycle.physical_cycle_view
            explanation = self.explanation_builder.explain(
                MPCDecisionExplanationInput(view)
            )
            self._require_explanation(explanation, view)
            formatted = self.explanation_formatter.format(
                MPCDecisionExplanationFormatInput(
                    explanation, source_input.explanation_locale
                )
            )
            self._require_formatted(formatted, explanation)
            record = self.journal_record_builder.build(
                ExplainableMPCDecisionJournalRecordInput(view, explanation, formatted)
            )
            self._require_record(record, view, explanation, formatted)
            row = self.csv_row_mapper.map(
                ExplainableMPCDecisionCSVRowMappingInput(record)
            )
            if not isinstance(row, ExplainableMPCDecisionCSVRow):
                raise TypeError(
                    "csv_row_mapper must return an ExplainableMPCDecisionCSVRow"
                )
            provenance = DecisionProvenance(
                context, cycle.decision.source_strategy, cycle.decision
            )
            feasible = self.feasibility.evaluate(cycle.decision, provenance=provenance)
            self._require_feasible(feasible, cycle, provenance)
            handoff = self.handoff.handoff(feasible)
            step = EMSIntegrationRunner._create_step(
                daily_input, index, battery_state, handoff
            )
            if simulation_traces:
                progressions.append(
                    SimulationStepProgression(
                        simulation_traces[-1], simulation_traces[-1].step_result, step
                    )
                )
            trace = self._execute_step(step, daily_input)
            daily_traces.append(
                RollingHeadroomAwareExplainableMPCDailySimulationStepTrace(
                    context,
                    horizon,
                    cycle,
                    view,
                    explanation,
                    formatted,
                    record,
                    row,
                    provenance,
                    feasible,
                    handoff,
                    trace,
                )
            )
            steps.append(step)
            simulation_traces.append(trace)
            records.append(record)
            rows.append(row)
            battery_state = trace.state.battery_result.next_state
            previous_grid_power_kw = trace.state.grid_result.actual_grid_power_kw

        simulation_result = DailySimulationResult(
            daily_input,
            SimulationScenario(tuple(steps)),
            tuple(simulation_traces),
            tuple(progressions),
        )
        csv_content = self.csv_serializer.serialize(tuple(rows))
        csv_file_result = self.csv_file_exporter.export(
            ExplainableMPCDecisionCSVFileExportInput(
                csv_content, source_input.decision_csv_output_path
            )
        )
        return RollingHeadroomAwareExplainableMPCDailySimulationResult(
            source_input,
            simulation_result,
            tuple(daily_traces),
            tuple(records),
            tuple(rows),
            csv_content,
            csv_file_result,
        )

    @staticmethod
    def _execute_step(
        step: SimulationStepInput, daily_input: DailySimulationScenarioInput
    ) -> SimulationExecutionTrace:
        from ems_simulator.explainable_mpc_daily import (
            ExplainableMPCDailySimulationRunner,
        )

        return ExplainableMPCDailySimulationRunner._execute_step(step, daily_input)

    @staticmethod
    def _require_cycle(result: object, source: PhysicallyAwareMPCCycleInput) -> None:
        if not isinstance(result, RollingHeadroomAwareMPCCycleResult):
            raise TypeError(
                "mpc_cycle_boundary must return RollingHeadroomAwareMPCCycleResult"
            )
        if result.source_input is not source:
            raise ValueError("rolling MPC cycle must preserve exact cycle input")

    @staticmethod
    def _require_explanation(
        explanation: object, view: PhysicallyAwareMPCCycleResult
    ) -> None:
        if not isinstance(explanation, MPCDecisionExplanation):
            raise TypeError("explanation_builder must return an MPCDecisionExplanation")
        if explanation.source_input.cycle_result is not view:
            raise ValueError("explanation must preserve exact physical cycle view")

    @staticmethod
    def _require_formatted(
        formatted: object, explanation: MPCDecisionExplanation
    ) -> None:
        if not isinstance(formatted, FormattedMPCDecisionExplanation):
            raise TypeError(
                "explanation_formatter must return FormattedMPCDecisionExplanation"
            )
        if formatted.source_input.explanation is not explanation:
            raise ValueError("formatted explanation must preserve exact explanation")

    @staticmethod
    def _require_record(
        record: object,
        view: PhysicallyAwareMPCCycleResult,
        explanation: MPCDecisionExplanation,
        formatted: FormattedMPCDecisionExplanation,
    ) -> None:
        if not isinstance(record, ExplainableMPCDecisionJournalRecord):
            raise TypeError(
                "journal_record_builder must return ExplainableMPCDecisionJournalRecord"
            )
        record_input = record.source_input
        if (
            record_input.cycle_result is not view
            or record_input.explanation is not explanation
        ):
            raise ValueError("journal record must preserve exact source artifacts")
        if record_input.formatted_explanation is not formatted:
            raise ValueError("journal record must preserve exact formatted explanation")

    @staticmethod
    def _require_feasible(
        feasible: object,
        cycle: RollingHeadroomAwareMPCCycleResult,
        provenance: DecisionProvenance,
    ) -> None:
        if not isinstance(feasible, FeasibleDecision):
            raise TypeError("feasibility must return a FeasibleDecision")
        if feasible.source_decision is not cycle.decision:
            raise ValueError("feasible decision must preserve exact rolling decision")
        if feasible.source_provenance is not provenance:
            raise ValueError("feasible decision must preserve exact provenance")
