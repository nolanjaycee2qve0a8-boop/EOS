"""Finite daily integration for TASK-159 economic schedule-aware MPC cycles.

The runner coordinates caller-owned facts only.  It does not calculate price,
schedule, reservation, or economic evidence: TASK-159 owns that single-cycle
path.  The physical cycle view is an exact compatibility artifact for the
existing explanation, journal, and CSV contracts, not a second MPC cycle.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ems_simulator.ems_integration import EMSIntegrationRunner
from ems_simulator.explainable_mpc_daily import ExplainableMPCDailySimulationRunner
from ems_simulator.input import HOURS_PER_DAY
from ems_simulator.multi_opportunity_explainable_mpc_daily import (
    MultiOpportunityExplainableMPCDailySimulationInput,
)
from ems_simulator.runner import DailySimulationResult
from ems_strategy import (
    ActuationHandoffBoundary,
    ActuationHandoffResult,
    DecisionProvenance,
    EconomicMultiOpportunityMPCCycleBoundary,
    EconomicMultiOpportunityMPCCycleInput,
    EconomicMultiOpportunityMPCCycleResult,
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
class EconomicMultiOpportunityExplainableMPCDailySimulationStepTrace:
    """Retain one TASK-159 outer cycle and exact downstream evidence."""

    context: EMSContext
    forecast_horizon: ForecastHorizon
    economic_multi_opportunity_mpc_cycle_result: EconomicMultiOpportunityMPCCycleResult
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
            (
                "economic_multi_opportunity_mpc_cycle_result",
                EconomicMultiOpportunityMPCCycleResult,
            ),
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

        cycle = self.economic_multi_opportunity_mpc_cycle_result
        view = self.physical_cycle_view
        physical_input = cycle.source_input.physical_cycle_input
        if physical_input.cycle_input.context is not self.context:
            raise ValueError("MPC cycle must preserve exact context identity")
        if physical_input.cycle_input.forecast_horizon is not self.forecast_horizon:
            raise ValueError("MPC cycle must preserve exact forecast identity")
        if view is not cycle.physical_cycle_view:
            raise ValueError("physical_cycle_view must be the exact compatibility view")
        if cycle.decision is not view.decision:
            raise ValueError("outer and physical views must preserve exact decision")
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
            raise ValueError("provenance must preserve exact outer decision")
        if self.feasible_decision.source_decision is not cycle.decision:
            raise ValueError("feasible decision must preserve exact outer decision")
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
class EconomicMultiOpportunityExplainableMPCDailySimulationResult:
    """Retain completed 24-hour evidence and one final CSV file effect.

    Existing CSV rows retain their stable physical explanation schema.  The
    full economic facts remain navigable through each outer cycle result and
    are intentionally not flattened into this compatibility CSV.
    """

    source_input: MultiOpportunityExplainableMPCDailySimulationInput
    simulation_result: DailySimulationResult
    step_traces: tuple[
        EconomicMultiOpportunityExplainableMPCDailySimulationStepTrace, ...
    ]
    journal_records: tuple[ExplainableMPCDecisionJournalRecord, ...]
    csv_rows: tuple[ExplainableMPCDecisionCSVRow, ...]
    csv_content: str
    csv_file_result: ExplainableMPCDecisionCSVFileExportResult

    def __post_init__(self) -> None:
        if not isinstance(
            self.source_input, MultiOpportunityExplainableMPCDailySimulationInput
        ):
            raise TypeError(
                "source_input must be a "
                "MultiOpportunityExplainableMPCDailySimulationInput"
            )
        if not isinstance(self.simulation_result, DailySimulationResult):
            raise TypeError("simulation_result must be a DailySimulationResult")
        for field_name, values, item_type in (
            (
                "step_traces",
                self.step_traces,
                EconomicMultiOpportunityExplainableMPCDailySimulationStepTrace,
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
        daily_input = self.source_input.daily_mpc_input.integration_input.daily_input
        if self.simulation_result.source_input is not daily_input:
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
        if (
            file_input.output_path
            is not self.source_input.daily_mpc_input.decision_csv_output_path
        ):
            raise ValueError("CSV file result must preserve exact output path")


class EconomicMultiOpportunityExplainableMPCDailySimulationBoundary(ABC):
    """Define one finite caller-requested economic schedule-aware day."""

    __slots__ = ()

    @abstractmethod
    def run(
        self, source_input: MultiOpportunityExplainableMPCDailySimulationInput
    ) -> EconomicMultiOpportunityExplainableMPCDailySimulationResult:
        """Run an explicit day without scheduling or hidden repetition."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class EconomicMultiOpportunityExplainableMPCDailySimulationRunner(
    EconomicMultiOpportunityExplainableMPCDailySimulationBoundary
):
    """Compose 24 TASK-159 cycles with actual simulator SOC/Grid feedback."""

    mpc_cycle_boundary: EconomicMultiOpportunityMPCCycleBoundary
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
            ("mpc_cycle_boundary", EconomicMultiOpportunityMPCCycleBoundary),
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
        self, source_input: MultiOpportunityExplainableMPCDailySimulationInput
    ) -> EconomicMultiOpportunityExplainableMPCDailySimulationResult:
        if not isinstance(
            source_input, MultiOpportunityExplainableMPCDailySimulationInput
        ):
            raise TypeError(
                "source_input must be a "
                "MultiOpportunityExplainableMPCDailySimulationInput"
            )
        daily_mpc_input = source_input.daily_mpc_input
        integration = daily_mpc_input.integration_input
        daily_input = integration.daily_input
        battery_state = BatterySimulationState(daily_input.initial_soc)
        previous_grid_power_kw = integration.initial_grid_power_kw
        steps: list[SimulationStepInput] = []
        simulation_traces: list[SimulationExecutionTrace] = []
        progressions: list[SimulationStepProgression] = []
        daily_traces: list[
            EconomicMultiOpportunityExplainableMPCDailySimulationStepTrace
        ] = []
        records: list[ExplainableMPCDecisionJournalRecord] = []
        rows: list[ExplainableMPCDecisionCSVRow] = []

        for index in range(HOURS_PER_DAY):
            context = EMSIntegrationRunner._create_context(
                integration, index, battery_state, previous_grid_power_kw
            )
            horizon = daily_mpc_input.forecast_horizons[index]
            physical_cycle_input = PhysicallyAwareMPCCycleInput(
                MPCCycleInput(
                    context,
                    horizon,
                    daily_mpc_input.mpc_configuration,
                    daily_mpc_input.optimization_objectives,
                    daily_mpc_input.source_strategy,
                ),
                BatteryOptimizationState(battery_state.soc),
                daily_mpc_input.battery_optimization_model,
            )
            cycle_input = EconomicMultiOpportunityMPCCycleInput(
                physical_cycle_input,
                source_input.candidate_configuration,
                source_input.opportunity_configuration,
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
                    explanation, daily_mpc_input.explanation_locale
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
            trace = ExplainableMPCDailySimulationRunner._execute_step(step, daily_input)
            daily_traces.append(
                EconomicMultiOpportunityExplainableMPCDailySimulationStepTrace(
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
        csv_rows = tuple(rows)
        csv_content = self.csv_serializer.serialize(csv_rows)
        csv_file_result = self.csv_file_exporter.export(
            ExplainableMPCDecisionCSVFileExportInput(
                csv_content, daily_mpc_input.decision_csv_output_path
            )
        )
        return EconomicMultiOpportunityExplainableMPCDailySimulationResult(
            source_input,
            simulation_result,
            tuple(daily_traces),
            tuple(records),
            csv_rows,
            csv_content,
            csv_file_result,
        )

    @staticmethod
    def _require_cycle(
        result: object,
        source: EconomicMultiOpportunityMPCCycleInput,
    ) -> None:
        if not isinstance(result, EconomicMultiOpportunityMPCCycleResult):
            raise TypeError(
                "mpc_cycle_boundary must return an "
                "EconomicMultiOpportunityMPCCycleResult"
            )
        if result.source_input is not source:
            raise ValueError("MPC cycle must preserve exact cycle input")

    @staticmethod
    def _require_explanation(
        explanation: object,
        view: PhysicallyAwareMPCCycleResult,
    ) -> None:
        if not isinstance(explanation, MPCDecisionExplanation):
            raise TypeError("explanation_builder must return an MPCDecisionExplanation")
        if explanation.source_input.cycle_result is not view:
            raise ValueError("explanation must preserve exact physical cycle view")

    @staticmethod
    def _require_formatted(
        formatted: object,
        explanation: MPCDecisionExplanation,
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
                "journal_record_builder must return an "
                "ExplainableMPCDecisionJournalRecord"
            )
        source = record.source_input
        if source.cycle_result is not view or source.explanation is not explanation:
            raise ValueError("journal record must preserve exact source artifacts")
        if source.formatted_explanation is not formatted:
            raise ValueError("journal record must preserve exact formatted explanation")

    @staticmethod
    def _require_feasible(
        feasible: object,
        cycle: EconomicMultiOpportunityMPCCycleResult,
        provenance: DecisionProvenance,
    ) -> None:
        if not isinstance(feasible, FeasibleDecision):
            raise TypeError("feasibility must return a FeasibleDecision")
        if feasible.source_decision is not cycle.decision:
            raise ValueError("feasible decision must preserve exact outer decision")
        if feasible.source_provenance is not provenance:
            raise ValueError("feasible decision must preserve exact provenance")
