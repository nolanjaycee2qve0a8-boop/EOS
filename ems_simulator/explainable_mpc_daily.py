"""Finite caller-driven daily MPC simulation application integration."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from ems_simulator.ems_integration import (
    EMSIntegrationRunner,
    EMSIntegrationScenarioInput,
)
from ems_simulator.input import HOURS_PER_DAY, DailySimulationScenarioInput
from ems_simulator.runner import DailySimulationResult
from ems_strategy import (
    ActuationHandoffBoundary,
    ActuationHandoffResult,
    DecisionProvenance,
    EMSContext,
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
    FormattedMPCDecisionExplanation,
    MPCConfiguration,
    MPCCycleInput,
    MPCDecisionExplanation,
    MPCDecisionExplanationBoundary,
    MPCDecisionExplanationFormatInput,
    MPCDecisionExplanationFormatterBoundary,
    MPCDecisionExplanationInput,
    MPCDecisionExplanationLocale,
    PhysicallyAwareMPCCycleBoundary,
    PhysicallyAwareMPCCycleInput,
    PhysicallyAwareMPCCycleResult,
)
from forecast import ForecastHorizon
from optimization import (
    BatteryOptimizationModel,
    BatteryOptimizationState,
    OptimizationObjectiveCollection,
)
from simulator import (
    BatterySimulationState,
    SimulationExecutionTrace,
    SimulationScenario,
    SimulationStepInput,
    SimulationStepProgression,
)


@dataclass(frozen=True, slots=True)
class ExplainableMPCDailySimulationInput:
    """Preserve every caller-owned fact for a finite 24-hour MPC simulation.

    Each horizon belongs to its corresponding simulation hour. The runner never
    shifts, pads, generates, or otherwise transforms that caller-owned tuple.
    """

    integration_input: EMSIntegrationScenarioInput
    forecast_horizons: tuple[ForecastHorizon, ...]
    mpc_configuration: MPCConfiguration
    optimization_objectives: OptimizationObjectiveCollection
    source_strategy: EMSStrategyDescriptor
    battery_optimization_model: BatteryOptimizationModel
    explanation_locale: MPCDecisionExplanationLocale
    decision_csv_output_path: Path

    def __post_init__(self) -> None:
        if not isinstance(self.integration_input, EMSIntegrationScenarioInput):
            raise TypeError("integration_input must be an EMSIntegrationScenarioInput")
        if not isinstance(self.forecast_horizons, tuple):
            raise TypeError("forecast_horizons must be a tuple")
        if len(self.forecast_horizons) != HOURS_PER_DAY:
            raise ValueError("forecast_horizons must contain exactly 24 values")
        if not isinstance(self.mpc_configuration, MPCConfiguration):
            raise TypeError("mpc_configuration must be an MPCConfiguration")
        if not isinstance(
            self.optimization_objectives, OptimizationObjectiveCollection
        ):
            raise TypeError(
                "optimization_objectives must be an OptimizationObjectiveCollection"
            )
        if not isinstance(self.source_strategy, EMSStrategyDescriptor):
            raise TypeError("source_strategy must be an EMSStrategyDescriptor")
        if not isinstance(self.battery_optimization_model, BatteryOptimizationModel):
            raise TypeError(
                "battery_optimization_model must be a BatteryOptimizationModel"
            )
        if self.explanation_locale not in ("zh-CN", "en-US"):
            raise ValueError("explanation_locale must be 'zh-CN' or 'en-US'")
        if not isinstance(self.decision_csv_output_path, Path):
            raise TypeError("decision_csv_output_path must be a pathlib.Path")
        # Reuse TASK-127's caller-owned path validation before any daily work.
        ExplainableMPCDecisionCSVFileExportInput("", self.decision_csv_output_path)

        daily_input = self.integration_input.daily_input
        model = self.battery_optimization_model
        parameters = daily_input.battery_parameters
        for field_name, actual, expected in (
            (
                "usable_capacity_kwh",
                model.usable_capacity_kwh,
                parameters.capacity_kwh,
            ),
            (
                "max_charge_power_kw",
                model.max_charge_power_kw,
                parameters.max_charge_power_kw,
            ),
            (
                "max_discharge_power_kw",
                model.max_discharge_power_kw,
                parameters.max_discharge_power_kw,
            ),
            (
                "charge_efficiency",
                model.charge_efficiency,
                parameters.charge_efficiency,
            ),
            (
                "discharge_efficiency",
                model.discharge_efficiency,
                parameters.discharge_efficiency,
            ),
            ("min_soc_fraction", model.min_soc_fraction, parameters.reserve_soc),
            ("max_soc_fraction", model.max_soc_fraction, 1.0),
        ):
            if actual != expected:
                raise ValueError(
                    f"battery_optimization_model.{field_name} must match "
                    "daily battery parameters"
                )

        for index, horizon in enumerate(self.forecast_horizons):
            if not isinstance(horizon, ForecastHorizon):
                raise TypeError(
                    "forecast_horizons must contain ForecastHorizon objects"
                )
            if len(horizon.points) != self.mpc_configuration.forecast_horizon_points:
                raise ValueError(
                    "each forecast horizon point count must equal "
                    "mpc_configuration.forecast_horizon_points"
                )
            # MPC first-step extraction requires one current planned step.
            if not horizon.points:
                raise ValueError("each forecast horizon must contain a first point")
            if (
                horizon.points[0].timestamp
                != daily_input.step_identities[index].timestamp
            ):
                raise ValueError(
                    "each first forecast point timestamp must align with its "
                    "daily simulation step"
                )


@dataclass(frozen=True, slots=True)
class ExplainableMPCDailySimulationStepTrace:
    """Preserve exact planning, explanation, and execution evidence for an hour."""

    context: EMSContext
    forecast_horizon: ForecastHorizon
    mpc_cycle_result: PhysicallyAwareMPCCycleResult
    explanation: MPCDecisionExplanation
    formatted_explanation: FormattedMPCDecisionExplanation
    journal_record: ExplainableMPCDecisionJournalRecord
    csv_row: ExplainableMPCDecisionCSVRow
    decision_provenance: DecisionProvenance
    feasible_decision: FeasibleDecision
    handoff: ActuationHandoffResult
    simulation_trace: SimulationExecutionTrace

    def __post_init__(self) -> None:
        if not isinstance(self.context, EMSContext):
            raise TypeError("context must be an EMSContext")
        if not isinstance(self.forecast_horizon, ForecastHorizon):
            raise TypeError("forecast_horizon must be a ForecastHorizon")
        if not isinstance(self.mpc_cycle_result, PhysicallyAwareMPCCycleResult):
            raise TypeError("mpc_cycle_result must be a PhysicallyAwareMPCCycleResult")
        if not isinstance(self.explanation, MPCDecisionExplanation):
            raise TypeError("explanation must be an MPCDecisionExplanation")
        if not isinstance(self.formatted_explanation, FormattedMPCDecisionExplanation):
            raise TypeError(
                "formatted_explanation must be a FormattedMPCDecisionExplanation"
            )
        if not isinstance(self.journal_record, ExplainableMPCDecisionJournalRecord):
            raise TypeError(
                "journal_record must be an ExplainableMPCDecisionJournalRecord"
            )
        if not isinstance(self.csv_row, ExplainableMPCDecisionCSVRow):
            raise TypeError("csv_row must be an ExplainableMPCDecisionCSVRow")
        if not isinstance(self.decision_provenance, DecisionProvenance):
            raise TypeError("decision_provenance must be a DecisionProvenance")
        if not isinstance(self.feasible_decision, FeasibleDecision):
            raise TypeError("feasible_decision must be a FeasibleDecision")
        if not isinstance(self.handoff, ActuationHandoffResult):
            raise TypeError("handoff must be an ActuationHandoffResult")
        if not isinstance(self.simulation_trace, SimulationExecutionTrace):
            raise TypeError("simulation_trace must be a SimulationExecutionTrace")
        cycle = self.mpc_cycle_result
        if cycle.source_input.cycle_input.context is not self.context:
            raise ValueError("MPC cycle must preserve exact context identity")
        if cycle.source_input.cycle_input.forecast_horizon is not self.forecast_horizon:
            raise ValueError("MPC cycle must preserve exact forecast identity")
        if self.explanation.source_input.cycle_result is not cycle:
            raise ValueError("explanation must preserve exact MPC cycle identity")
        if self.formatted_explanation.source_input.explanation is not self.explanation:
            raise ValueError("formatted explanation must preserve exact explanation")
        record_input = self.journal_record.source_input
        if record_input.cycle_result is not cycle:
            raise ValueError("journal record must preserve exact MPC cycle identity")
        if record_input.explanation is not self.explanation:
            raise ValueError("journal record must preserve exact explanation identity")
        if record_input.formatted_explanation is not self.formatted_explanation:
            raise ValueError("journal record must preserve exact formatted explanation")
        decision = cycle.decision
        if self.decision_provenance.decision is not decision:
            raise ValueError("provenance must preserve exact MPC decision identity")
        if self.feasible_decision.source_decision is not decision:
            raise ValueError("feasible decision must preserve exact MPC decision")
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
class ExplainableMPCDailySimulationResult:
    """Retain completed daily planning evidence and one final CSV file effect.

    Journal records and CSV rows describe the MPC decision request, whereas
    the step trace separately retains downstream feasible decision, handoff,
    and simulation evidence. They are intentionally not an execution log.
    """

    source_input: ExplainableMPCDailySimulationInput
    simulation_result: DailySimulationResult
    step_traces: tuple[ExplainableMPCDailySimulationStepTrace, ...]
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
        for field_name, value, expected_type in (
            (
                "step_traces",
                self.step_traces,
                ExplainableMPCDailySimulationStepTrace,
            ),
            (
                "journal_records",
                self.journal_records,
                ExplainableMPCDecisionJournalRecord,
            ),
            ("csv_rows", self.csv_rows, ExplainableMPCDecisionCSVRow),
        ):
            if not isinstance(value, tuple):
                raise TypeError(f"{field_name} must be a tuple")
            if len(value) != HOURS_PER_DAY:
                raise ValueError(f"{field_name} must contain exactly 24 values")
            if any(not isinstance(item, expected_type) for item in value):
                raise TypeError(f"{field_name} must contain {expected_type.__name__}")
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
            raise ValueError("simulation_result must preserve exact daily input")
        for index, trace in enumerate(self.step_traces):
            if trace.journal_record is not self.journal_records[index]:
                raise ValueError("step trace must preserve exact journal record")
            if trace.csv_row is not self.csv_rows[index]:
                raise ValueError("step trace must preserve exact CSV row")
            if trace.simulation_trace is not self.simulation_result.traces[index]:
                raise ValueError("step trace must preserve exact simulation trace")
        file_input = self.csv_file_result.source_input
        if file_input.csv_content != self.csv_content:
            raise ValueError("CSV file result must preserve exact CSV content")
        if file_input.output_path is not self.source_input.decision_csv_output_path:
            raise ValueError("CSV file result must preserve exact output path")


class ExplainableMPCDailySimulationBoundary(ABC):
    """Define one finite, caller-requested 24-step MPC simulation run."""

    __slots__ = ()

    @abstractmethod
    def run(
        self,
        source_input: ExplainableMPCDailySimulationInput,
    ) -> ExplainableMPCDailySimulationResult:
        """Run the explicit finite day without scheduling or automatic repetition."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class ExplainableMPCDailySimulationRunner(ExplainableMPCDailySimulationBoundary):
    """Compose existing seams into one explicit, stop-first 24-hour flow."""

    mpc_cycle_boundary: PhysicallyAwareMPCCycleBoundary
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
            ("mpc_cycle_boundary", PhysicallyAwareMPCCycleBoundary),
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
        self,
        source_input: ExplainableMPCDailySimulationInput,
    ) -> ExplainableMPCDailySimulationResult:
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
        daily_traces: list[ExplainableMPCDailySimulationStepTrace] = []
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
            cycle_result = self.mpc_cycle_boundary.run_cycle(cycle_input)
            self._require_cycle(cycle_result, cycle_input)
            explanation = self.explanation_builder.explain(
                MPCDecisionExplanationInput(cycle_result)
            )
            self._require_explanation(explanation, cycle_result)
            formatted = self.explanation_formatter.format(
                MPCDecisionExplanationFormatInput(
                    explanation, source_input.explanation_locale
                )
            )
            self._require_formatted(formatted, explanation)
            record = self.journal_record_builder.build(
                ExplainableMPCDecisionJournalRecordInput(
                    cycle_result, explanation, formatted
                )
            )
            self._require_record(record, cycle_result, explanation, formatted)
            row = self.csv_row_mapper.map(
                ExplainableMPCDecisionCSVRowMappingInput(record)
            )
            if not isinstance(row, ExplainableMPCDecisionCSVRow):
                raise TypeError(
                    "csv_row_mapper must return an ExplainableMPCDecisionCSVRow"
                )
            provenance = DecisionProvenance(
                context, cycle_result.decision.source_strategy, cycle_result.decision
            )
            feasible = self.feasibility.evaluate(
                cycle_result.decision, provenance=provenance
            )
            self._require_feasible(feasible, cycle_result, provenance)
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
            daily_trace = ExplainableMPCDailySimulationStepTrace(
                context,
                horizon,
                cycle_result,
                explanation,
                formatted,
                record,
                row,
                provenance,
                feasible,
                handoff,
                trace,
            )
            steps.append(step)
            simulation_traces.append(trace)
            daily_traces.append(daily_trace)
            records.append(record)
            rows.append(row)
            battery_state = trace.state.battery_result.next_state
            previous_grid_power_kw = trace.state.grid_result.actual_grid_power_kw

        scenario = SimulationScenario(tuple(steps))
        simulation_result = DailySimulationResult(
            daily_input, scenario, tuple(simulation_traces), tuple(progressions)
        )
        csv_rows = tuple(rows)
        csv_content = self.csv_serializer.serialize(csv_rows)
        export_result = self.csv_file_exporter.export(
            ExplainableMPCDecisionCSVFileExportInput(
                csv_content, source_input.decision_csv_output_path
            )
        )
        return ExplainableMPCDailySimulationResult(
            source_input,
            simulation_result,
            tuple(daily_traces),
            tuple(records),
            csv_rows,
            csv_content,
            export_result,
        )

    @staticmethod
    def _execute_step(
        step: SimulationStepInput,
        daily_input: DailySimulationScenarioInput,
    ) -> SimulationExecutionTrace:
        # Reuse the existing deterministic simulator composition unchanged.
        if not isinstance(daily_input, DailySimulationScenarioInput):
            raise TypeError("daily_input must be a DailySimulationScenarioInput")
        from ems_simulator.battery import SimpleBatteryPhysicsModel
        from ems_simulator.load import LoadProfileSimulationModel
        from ems_simulator.pv import PVProfileSimulationModel

        return EMSIntegrationRunner._execute_step(
            step,
            PVProfileSimulationModel(),
            LoadProfileSimulationModel(),
            SimpleBatteryPhysicsModel(daily_input.battery_parameters),
        )

    @staticmethod
    def _require_cycle(result: object, source: PhysicallyAwareMPCCycleInput) -> None:
        if not isinstance(result, PhysicallyAwareMPCCycleResult):
            raise TypeError(
                "mpc_cycle_boundary must return PhysicallyAwareMPCCycleResult"
            )
        if result.source_input is not source:
            raise ValueError("MPC cycle result must preserve exact cycle input")

    @staticmethod
    def _require_explanation(
        explanation: object, cycle: PhysicallyAwareMPCCycleResult
    ) -> None:
        if not isinstance(explanation, MPCDecisionExplanation):
            raise TypeError("explanation_builder must return an MPCDecisionExplanation")
        if explanation.source_input.cycle_result is not cycle:
            raise ValueError("explanation must preserve exact cycle result")

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
        cycle: PhysicallyAwareMPCCycleResult,
        explanation: MPCDecisionExplanation,
        formatted: FormattedMPCDecisionExplanation,
    ) -> None:
        if not isinstance(record, ExplainableMPCDecisionJournalRecord):
            raise TypeError(
                "journal_record_builder must return ExplainableMPCDecisionJournalRecord"
            )
        source = record.source_input
        if source.cycle_result is not cycle or source.explanation is not explanation:
            raise ValueError("journal record must preserve exact source artifacts")
        if source.formatted_explanation is not formatted:
            raise ValueError("journal record must preserve exact formatted explanation")

    @staticmethod
    def _require_feasible(
        feasible: object,
        cycle: PhysicallyAwareMPCCycleResult,
        provenance: DecisionProvenance,
    ) -> None:
        if not isinstance(feasible, FeasibleDecision):
            raise TypeError("feasibility must return a FeasibleDecision")
        if feasible.source_decision is not cycle.decision:
            raise ValueError("feasible decision must preserve exact MPC decision")
        if feasible.source_provenance is not provenance:
            raise ValueError("feasible decision must preserve exact provenance")
