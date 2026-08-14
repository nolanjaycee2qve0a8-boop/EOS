"""Observe full, rolling, and schedule-aware headroom behavior on TASK-146 facts.

The module is measurement-only.  It reuses frozen full/rolling runners and the
TASK-152 schedule-aware runner, then reads their retained provenance into one
deterministic comparison read model.  It owns neither headroom accounting nor
control logic.
"""

import argparse
import csv
from collections.abc import Sequence
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Protocol

from ems_simulator.explainable_mpc_daily import ExplainableMPCDailySimulationInput
from ems_simulator.headroom_aware_explainable_mpc_daily import (
    HeadroomAwareExplainableMPCDailySimulationResult,
)
from ems_simulator.headroom_aware_mpc_demo import _runner as _full_runner
from ems_simulator.multi_opportunity_explainable_mpc_daily import (
    MultiOpportunityExplainableMPCDailySimulationInput,
    MultiOpportunityExplainableMPCDailySimulationResult,
    MultiOpportunityExplainableMPCDailySimulationRunner,
)
from ems_simulator.multi_opportunity_headroom_demo import (
    _GAP_TOLERANCE_POINTS,
    create_demo_input,
)
from ems_simulator.net_load_mpc_demo import (
    _DemoMPCDecisionTranslator,
    _DemoPassThroughFeasibility,
    _DemoSimulationHandoff,
)
from ems_simulator.output import SimulationResultExporter
from ems_simulator.rolling_headroom_aware_explainable_mpc_daily import (
    RollingHeadroomAwareExplainableMPCDailySimulationResult,
)
from ems_simulator.rolling_headroom_mpc_demo import _rolling_runner
from ems_strategy import (
    DeterministicExplainableMPCDecisionCSVFileExporter,
    DeterministicExplainableMPCDecisionCSVRowMapper,
    DeterministicExplainableMPCDecisionCSVSerializer,
    DeterministicExplainableMPCDecisionJournalRecordBuilder,
    DeterministicMPCDecisionExplanationBuilder,
    DeterministicMPCDecisionExplanationFormatter,
    FirstStepMPCCurrentActionExtractor,
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
    HeadroomAwarePhysicalOptimizationSolveOutput,
    MultiOpportunityHeadroomScheduleEntry,
    MultiOpportunityPhysicalOptimizationSolveOutput,
    NetLoadAwareBaselineOptimizationConfiguration,
    NetLoadAwareBaselineOptimizer,
    OptimizationSolutionControlPlanBuilder,
    PVOpportunityWindowConfiguration,
    RollingHeadroomAwarePhysicalOptimizationSolveOutput,
    RollingPVHeadroomRequirement,
)

_CANDIDATE_CONFIGURATION = NetLoadAwareBaselineOptimizationConfiguration(0.3, 0.8, 3.0)
_OPPORTUNITY_CONFIGURATION = PVOpportunityWindowConfiguration(_GAP_TOLERANCE_POINTS)

type _DailyComparisonResult = (
    HeadroomAwareExplainableMPCDailySimulationResult
    | RollingHeadroomAwareExplainableMPCDailySimulationResult
    | MultiOpportunityExplainableMPCDailySimulationResult
)


class _GridChargeReservationEvidence(Protocol):
    @property
    def requested_grid_charge_power_kw(self) -> float: ...

    @property
    def allowed_grid_charge_power_kw(self) -> float: ...

    @property
    def reservation_applied(self) -> bool: ...


_CSV_COLUMNS = (
    "timestamp",
    "full_actual_soc",
    "rolling_actual_soc",
    "schedule_actual_soc",
    "full_required_headroom_kwh",
    "rolling_required_headroom_kwh",
    "schedule_first_standalone_headroom_kwh",
    "schedule_first_adjusted_headroom_kwh",
    "full_target_soc",
    "rolling_target_soc",
    "schedule_target_soc",
    "rolling_opportunity_start",
    "rolling_opportunity_end",
    "schedule_opportunity_count",
    "schedule_first_opportunity_start",
    "schedule_first_opportunity_end",
    "schedule_gap_load_energy_kwh",
    "schedule_stored_depletion_potential_kwh",
    "full_requested_grid_charge_kw",
    "rolling_requested_grid_charge_kw",
    "schedule_requested_grid_charge_kw",
    "full_allowed_grid_charge_kw",
    "rolling_allowed_grid_charge_kw",
    "schedule_allowed_grid_charge_kw",
    "full_actual_battery_power_kw",
    "rolling_actual_battery_power_kw",
    "schedule_actual_battery_power_kw",
    "full_actual_grid_power_kw",
    "rolling_actual_grid_power_kw",
    "schedule_actual_grid_power_kw",
    "full_next_soc",
    "rolling_next_soc",
    "schedule_next_soc",
)


@dataclass(frozen=True, slots=True)
class ComparisonMetrics:
    """Read-only observed daily metrics for one comparison path."""

    pv_energy_kwh: float
    load_energy_kwh: float
    battery_throughput_kwh: float
    grid_import_energy_kwh: float
    grid_export_energy_kwh: float
    final_soc: float
    charge_decisions: int
    discharge_decisions: int
    idle_decisions: int
    revised_decisions: int
    soc_limited_decisions: int
    power_limited_decisions: int
    reservation_count: int
    reduced_reservation_count: int
    zeroed_reservation_count: int
    minimum_target_soc: float
    maximum_required_headroom_kwh: float


@dataclass(frozen=True, slots=True)
class PVAbsorptionMetrics:
    """Use TASK-146's observed actual-power PV absorption accounting."""

    total_pv_surplus_energy_kwh: float
    estimated_absorbed_pv_surplus_energy_kwh: float


@dataclass(frozen=True, slots=True)
class ScheduleEvidenceMetrics:
    """Read-only aggregate observations from exact TASK-152 schedule evidence."""

    maximum_opportunity_entries: int
    no_opportunity_cycle_count: int
    minimum_first_standalone_headroom_kwh: float | None
    maximum_first_standalone_headroom_kwh: float | None
    minimum_first_adjusted_headroom_kwh: float | None
    maximum_first_adjusted_headroom_kwh: float | None
    maximum_stored_depletion_potential_kwh: float


@dataclass(frozen=True, slots=True)
class ScheduleAwareHeadroomComparisonExecutionResult:
    """Retain three completed paths and deterministic diagnostic artifacts."""

    full_source_input: ExplainableMPCDailySimulationInput
    rolling_source_input: ExplainableMPCDailySimulationInput
    schedule_source_input: MultiOpportunityExplainableMPCDailySimulationInput
    full_result: HeadroomAwareExplainableMPCDailySimulationResult
    rolling_result: RollingHeadroomAwareExplainableMPCDailySimulationResult
    schedule_result: MultiOpportunityExplainableMPCDailySimulationResult
    full_metrics: ComparisonMetrics
    rolling_metrics: ComparisonMetrics
    schedule_metrics: ComparisonMetrics
    full_pv_absorption: PVAbsorptionMetrics
    rolling_pv_absorption: PVAbsorptionMetrics
    schedule_pv_absorption: PVAbsorptionMetrics
    schedule_evidence_metrics: ScheduleEvidenceMetrics
    comparison_csv_path: Path
    summary_path: Path
    target_svg_path: Path
    required_headroom_svg_path: Path
    soc_svg_path: Path
    grid_svg_path: Path


def run_demo(output_directory: Path) -> ScheduleAwareHeadroomComparisonExecutionResult:
    """Run the three existing application paths on the same finite facts."""

    if not isinstance(output_directory, Path):
        raise TypeError("output_directory must be a pathlib.Path")
    full_source = create_demo_input(output_directory)
    return run_comparison(full_source, output_directory)


def run_comparison(
    full_source: ExplainableMPCDailySimulationInput,
    output_directory: Path,
) -> ScheduleAwareHeadroomComparisonExecutionResult:
    """Run frozen three-path execution for one caller-owned scenario input.

    This composition helper owns only path cloning and deterministic read-model
    export.  Planning, reservation, physical revision, and daily execution
    remain within the existing TASK-138, TASK-144, and TASK-152 runners.
    """

    if not isinstance(full_source, ExplainableMPCDailySimulationInput):
        raise TypeError("full_source must be an ExplainableMPCDailySimulationInput")
    if not isinstance(output_directory, Path):
        raise TypeError("output_directory must be a pathlib.Path")
    output_directory.mkdir(parents=True, exist_ok=True)
    rolling_source = ExplainableMPCDailySimulationInput(
        full_source.integration_input,
        full_source.forecast_horizons,
        full_source.mpc_configuration,
        full_source.optimization_objectives,
        full_source.source_strategy,
        full_source.battery_optimization_model,
        full_source.explanation_locale,
        output_directory / "rolling_mpc_decisions.csv",
    )
    schedule_daily_source = ExplainableMPCDailySimulationInput(
        full_source.integration_input,
        full_source.forecast_horizons,
        full_source.mpc_configuration,
        full_source.optimization_objectives,
        full_source.source_strategy,
        full_source.battery_optimization_model,
        full_source.explanation_locale,
        output_directory / "schedule_mpc_decisions.csv",
    )
    schedule_source = MultiOpportunityExplainableMPCDailySimulationInput(
        schedule_daily_source,
        _CANDIDATE_CONFIGURATION,
        _OPPORTUNITY_CONFIGURATION,
    )

    full_result = _full_runner().run(full_source)
    rolling_result = _rolling_runner().run(rolling_source)
    schedule_result = _schedule_runner().run(schedule_source)
    full_metrics = _full_metrics(full_result)
    rolling_metrics = _rolling_metrics(rolling_result)
    schedule_metrics = _schedule_metrics(schedule_result)
    full_pv = _pv_absorption(full_result)
    rolling_pv = _pv_absorption(rolling_result)
    schedule_pv = _pv_absorption(schedule_result)
    schedule_evidence = _schedule_evidence_metrics(schedule_result)

    comparison_csv_path = output_directory / "schedule_aware_headroom_comparison.csv"
    comparison_csv_path.write_text(
        _comparison_csv(full_result, rolling_result, schedule_result),
        encoding="utf-8",
        newline="",
    )
    target_svg_path = output_directory / "recommended_soc_target.svg"
    required_headroom_svg_path = output_directory / "required_headroom_comparison.svg"
    soc_svg_path = output_directory / "soc_comparison.svg"
    grid_svg_path = output_directory / "grid_power_comparison.svg"
    target_svg_path.write_text(
        _target_svg(full_result, rolling_result, schedule_result),
        encoding="utf-8",
        newline="",
    )
    required_headroom_svg_path.write_text(
        _headroom_svg(full_result, rolling_result, schedule_result),
        encoding="utf-8",
        newline="",
    )
    soc_svg_path.write_text(
        _soc_svg(full_result, rolling_result, schedule_result),
        encoding="utf-8",
        newline="",
    )
    grid_svg_path.write_text(
        _grid_svg(full_result, rolling_result, schedule_result),
        encoding="utf-8",
        newline="",
    )
    summary_path = output_directory / "daily_summary.txt"
    summary_path.write_text(
        _summary_text(
            full_result,
            rolling_result,
            schedule_result,
            full_metrics,
            rolling_metrics,
            schedule_metrics,
            full_pv,
            rolling_pv,
            schedule_pv,
            schedule_evidence,
        ),
        encoding="utf-8",
        newline="",
    )
    return ScheduleAwareHeadroomComparisonExecutionResult(
        full_source,
        rolling_source,
        schedule_source,
        full_result,
        rolling_result,
        schedule_result,
        full_metrics,
        rolling_metrics,
        schedule_metrics,
        full_pv,
        rolling_pv,
        schedule_pv,
        schedule_evidence,
        comparison_csv_path,
        summary_path,
        target_svg_path,
        required_headroom_svg_path,
        soc_svg_path,
        grid_svg_path,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the finite three-path behavioral comparison CLI."""

    parser = argparse.ArgumentParser(
        description="EOS full, rolling, and schedule-aware headroom comparison"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("simulation_output_task153_schedule_aware"),
        help="directory for deterministic schedule-aware comparison outputs",
    )
    arguments = parser.parse_args(argv)
    execution = run_demo(arguments.output_dir)
    for path in (
        execution.comparison_csv_path,
        execution.summary_path,
        execution.target_svg_path,
        execution.required_headroom_svg_path,
        execution.soc_svg_path,
        execution.grid_svg_path,
    ):
        print(path)
    return 0


def _schedule_runner() -> MultiOpportunityExplainableMPCDailySimulationRunner:
    """Compose existing TASK-147--152 boundaries without adding planning logic."""

    optimizer = DeterministicMultiOpportunityPhysicalOptimizer(
        DeterministicMultiOpportunityHeadroomScheduleCalculator(
            DeterministicPVOpportunitySequenceCalculator(),
            DeterministicPVHeadroomRequirementCalculator(),
        ),
        DeterministicMultiOpportunityCandidatePlanner(
            NetLoadAwareBaselineOptimizer(_CANDIDATE_CONFIGURATION),
            DeterministicMultiOpportunityGridChargeReservationCalculator(),
        ),
        DeterministicExplicitCandidatePhysicalReviser(
            DeterministicBatterySOCHorizonProjector(),
            DeterministicBatterySOCHorizonConstraintEvaluator(),
            DeterministicBatteryPowerHorizonConstraintEvaluator(),
            DeterministicBatteryHorizonConstraintAggregator(),
        ),
    )
    cycle = MultiOpportunitySingleMPCCycleOrchestrator(
        optimizer,
        OptimizationSolutionControlPlanBuilder(),
        FirstStepMPCCurrentActionExtractor(),
        _DemoMPCDecisionTranslator(),
    )
    return MultiOpportunityExplainableMPCDailySimulationRunner(
        cycle,
        DeterministicMPCDecisionExplanationBuilder(),
        DeterministicMPCDecisionExplanationFormatter(),
        DeterministicExplainableMPCDecisionJournalRecordBuilder(),
        DeterministicExplainableMPCDecisionCSVRowMapper(),
        DeterministicExplainableMPCDecisionCSVSerializer(),
        DeterministicExplainableMPCDecisionCSVFileExporter(),
        _DemoPassThroughFeasibility(),
        _DemoSimulationHandoff(),
    )


def _full_metrics(
    result: HeadroomAwareExplainableMPCDailySimulationResult,
) -> ComparisonMetrics:
    outputs = tuple(
        trace.headroom_mpc_cycle_result.headroom_optimization_output
        for trace in result.step_traces
    )
    return _metrics(
        result,
        tuple(
            output.headroom_requirement.recommended_pre_pv_max_soc_fraction
            for output in outputs
        ),
        tuple(
            output.headroom_requirement.required_headroom_energy_kwh
            for output in outputs
        ),
        tuple(
            output.candidate_planning_result.grid_charge_reservation
            for output in outputs
            if output.candidate_planning_result.grid_charge_reservation is not None
        ),
    )


def _rolling_metrics(
    result: RollingHeadroomAwareExplainableMPCDailySimulationResult,
) -> ComparisonMetrics:
    outputs = tuple(
        trace.rolling_headroom_mpc_cycle_result.rolling_headroom_optimization_output
        for trace in result.step_traces
    )
    requirements = tuple(
        output.rolling_headroom_requirement.headroom_requirement for output in outputs
    )
    return _metrics(
        result,
        tuple(
            requirement.recommended_pre_pv_max_soc_fraction
            for requirement in requirements
        ),
        tuple(requirement.required_headroom_energy_kwh for requirement in requirements),
        tuple(
            output.candidate_planning_result.grid_charge_reservation
            for output in outputs
            if output.candidate_planning_result.grid_charge_reservation is not None
        ),
    )


def _schedule_metrics(
    result: MultiOpportunityExplainableMPCDailySimulationResult,
) -> ComparisonMetrics:
    outputs = tuple(
        trace.multi_opportunity_mpc_cycle_result.multi_opportunity_optimization_output
        for trace in result.step_traces
    )
    entries = tuple(
        output.headroom_schedule.entries[0]
        for output in outputs
        if output.headroom_schedule.entries
    )
    return _metrics(
        result,
        tuple(entry.recommended_pre_opportunity_max_soc_fraction for entry in entries),
        tuple(entry.required_pre_opportunity_headroom_kwh for entry in entries),
        tuple(
            output.candidate_planning_result.reservation_result
            for output in outputs
            if output.candidate_planning_result.reservation_result is not None
        ),
    )


def _schedule_evidence_metrics(
    result: MultiOpportunityExplainableMPCDailySimulationResult,
) -> ScheduleEvidenceMetrics:
    schedules = tuple(
        trace.multi_opportunity_mpc_cycle_result.multi_opportunity_optimization_output.headroom_schedule
        for trace in result.step_traces
    )
    first_entries = tuple(
        schedule.entries[0] for schedule in schedules if schedule.entries
    )
    standalone = tuple(
        entry.headroom_requirement.required_headroom_energy_kwh
        for entry in first_entries
    )
    adjusted = tuple(
        entry.required_pre_opportunity_headroom_kwh for entry in first_entries
    )
    depletion = tuple(
        entry.battery_stored_energy_depletion_potential_kwh for entry in first_entries
    )
    return ScheduleEvidenceMetrics(
        max((len(schedule.entries) for schedule in schedules), default=0),
        sum(not schedule.entries for schedule in schedules),
        min(standalone) if standalone else None,
        max(standalone) if standalone else None,
        min(adjusted) if adjusted else None,
        max(adjusted) if adjusted else None,
        max(depletion, default=0.0),
    )


def _metrics(
    result: _DailyComparisonResult,
    targets: tuple[float, ...],
    headrooms: tuple[float, ...],
    reservations: tuple[_GridChargeReservationEvidence, ...],
) -> ComparisonMetrics:
    simulation_result = result.simulation_result
    summary = SimulationResultExporter.export(simulation_result).summary
    records = result.journal_records
    reasons = tuple(reason for record in records for reason in record.revision_reasons)
    return ComparisonMetrics(
        summary.pv_energy_kwh,
        summary.load_energy_kwh,
        summary.battery_throughput_kwh,
        summary.grid_import_energy_kwh,
        summary.grid_export_energy_kwh,
        simulation_result.traces[-1].state.battery_result.next_state.soc,
        sum(record.final_action.action == "charge" for record in records),
        sum(record.final_action.action == "discharge" for record in records),
        sum(record.final_action.action == "idle" for record in records),
        sum(record.revision_applied for record in records),
        sum(reason in {"min_soc_limit", "max_soc_limit"} for reason in reasons),
        sum(
            reason in {"charge_power_limit", "discharge_power_limit"}
            for reason in reasons
        ),
        len(reservations),
        sum(_reservation_applied(reservation) for reservation in reservations),
        sum(_reservation_allowed(reservation) == 0.0 for reservation in reservations),
        min(targets, default=1.0),
        max(headrooms, default=0.0),
    )


def _comparison_csv(
    full: HeadroomAwareExplainableMPCDailySimulationResult,
    rolling: RollingHeadroomAwareExplainableMPCDailySimulationResult,
    schedule: MultiOpportunityExplainableMPCDailySimulationResult,
) -> str:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(_CSV_COLUMNS)
    for full_trace, rolling_trace, schedule_trace in zip(
        full.step_traces, rolling.step_traces, schedule.step_traces, strict=True
    ):
        full_output = full_trace.headroom_mpc_cycle_result.headroom_optimization_output
        rolling_cycle = rolling_trace.rolling_headroom_mpc_cycle_result
        schedule_cycle = schedule_trace.multi_opportunity_mpc_cycle_result
        rolling_output = rolling_cycle.rolling_headroom_optimization_output
        schedule_output = schedule_cycle.multi_opportunity_optimization_output
        full_requirement = full_output.headroom_requirement
        rolling_requirement = rolling_output.rolling_headroom_requirement
        schedule_entry = (
            schedule_output.headroom_schedule.entries[0]
            if schedule_output.headroom_schedule.entries
            else None
        )
        timestamp = full_trace.simulation_trace.simulation_input.step_identity.timestamp
        if timestamp is None:
            raise ValueError("comparison requires explicit timestamps")
        writer.writerow(
            (
                timestamp.isoformat(),
                _number(
                    full_trace.headroom_mpc_cycle_result.source_input.battery_state.soc_fraction
                ),
                _number(
                    rolling_trace.rolling_headroom_mpc_cycle_result.source_input.battery_state.soc_fraction
                ),
                _number(
                    schedule_trace.multi_opportunity_mpc_cycle_result.source_input.physical_cycle_input.battery_state.soc_fraction
                ),
                _number(full_requirement.required_headroom_energy_kwh),
                _number(
                    rolling_requirement.headroom_requirement.required_headroom_energy_kwh
                ),
                _entry_value(
                    schedule_entry,
                    "headroom_requirement.required_headroom_energy_kwh",
                ),
                _entry_value(schedule_entry, "required_pre_opportunity_headroom_kwh"),
                _number(full_requirement.recommended_pre_pv_max_soc_fraction),
                _number(
                    rolling_requirement.headroom_requirement.recommended_pre_pv_max_soc_fraction
                ),
                _entry_value(
                    schedule_entry,
                    "recommended_pre_opportunity_max_soc_fraction",
                ),
                _rolling_window_value(rolling_requirement, "start"),
                _rolling_window_value(rolling_requirement, "end"),
                ""
                if schedule_entry is None
                else str(len(schedule_output.headroom_schedule.entries)),
                _entry_window_value(schedule_entry, "start"),
                _entry_window_value(schedule_entry, "end"),
                _entry_value(schedule_entry, "gap_net_deficit_load_energy_kwh"),
                _entry_value(
                    schedule_entry, "battery_stored_energy_depletion_potential_kwh"
                ),
                _reservation_value(
                    full_output.candidate_planning_result.grid_charge_reservation,
                    "requested_grid_charge_power_kw",
                ),
                _reservation_value(
                    rolling_output.candidate_planning_result.grid_charge_reservation,
                    "requested_grid_charge_power_kw",
                ),
                _reservation_value(
                    schedule_output.candidate_planning_result.reservation_result,
                    "requested_grid_charge_power_kw",
                ),
                _reservation_value(
                    full_output.candidate_planning_result.grid_charge_reservation,
                    "allowed_grid_charge_power_kw",
                ),
                _reservation_value(
                    rolling_output.candidate_planning_result.grid_charge_reservation,
                    "allowed_grid_charge_power_kw",
                ),
                _reservation_value(
                    schedule_output.candidate_planning_result.reservation_result,
                    "allowed_grid_charge_power_kw",
                ),
                _number(
                    full_trace.simulation_trace.state.battery_result.actual_power_kw
                ),
                _number(
                    rolling_trace.simulation_trace.state.battery_result.actual_power_kw
                ),
                _number(
                    schedule_trace.simulation_trace.state.battery_result.actual_power_kw
                ),
                _number(
                    full_trace.simulation_trace.state.grid_result.actual_grid_power_kw
                ),
                _number(
                    rolling_trace.simulation_trace.state.grid_result.actual_grid_power_kw
                ),
                _number(
                    schedule_trace.simulation_trace.state.grid_result.actual_grid_power_kw
                ),
                _number(
                    full_trace.simulation_trace.state.battery_result.next_state.soc
                ),
                _number(
                    rolling_trace.simulation_trace.state.battery_result.next_state.soc
                ),
                _number(
                    schedule_trace.simulation_trace.state.battery_result.next_state.soc
                ),
            )
        )
    return stream.getvalue()


def _target_svg(
    full: HeadroomAwareExplainableMPCDailySimulationResult,
    rolling: RollingHeadroomAwareExplainableMPCDailySimulationResult,
    schedule: MultiOpportunityExplainableMPCDailySimulationResult,
) -> str:
    return _three_series_svg(
        "Recommended target SOC",
        (
            ("Full", _full_targets(full), "#2563eb"),
            ("Rolling", _rolling_targets(rolling), "#dc2626"),
            ("Schedule-aware", _schedule_targets(schedule), "#059669"),
        ),
        0.0,
        1.0,
    )


def _headroom_svg(
    full: HeadroomAwareExplainableMPCDailySimulationResult,
    rolling: RollingHeadroomAwareExplainableMPCDailySimulationResult,
    schedule: MultiOpportunityExplainableMPCDailySimulationResult,
) -> str:
    series = (
        ("Full", _full_headrooms(full), "#2563eb"),
        ("Rolling", _rolling_headrooms(rolling), "#dc2626"),
        ("Schedule-aware", _schedule_headrooms(schedule), "#059669"),
    )
    maximum = max(
        1.0,
        *(value for _, values, _ in series for value in values if value is not None),
    )
    return _three_series_svg("Required headroom (kWh)", series, 0.0, maximum)


def _soc_svg(
    full: HeadroomAwareExplainableMPCDailySimulationResult,
    rolling: RollingHeadroomAwareExplainableMPCDailySimulationResult,
    schedule: MultiOpportunityExplainableMPCDailySimulationResult,
) -> str:
    return _three_series_svg(
        "Actual SOC",
        (
            ("Full", _next_socs(full), "#2563eb"),
            ("Rolling", _next_socs(rolling), "#dc2626"),
            ("Schedule-aware", _next_socs(schedule), "#059669"),
        ),
        0.0,
        1.0,
    )


def _grid_svg(
    full: HeadroomAwareExplainableMPCDailySimulationResult,
    rolling: RollingHeadroomAwareExplainableMPCDailySimulationResult,
    schedule: MultiOpportunityExplainableMPCDailySimulationResult,
) -> str:
    series = (
        ("Full", _grid_values(full), "#2563eb"),
        ("Rolling", _grid_values(rolling), "#dc2626"),
        ("Schedule-aware", _grid_values(schedule), "#059669"),
    )
    maximum = max(
        1.0,
        *(
            abs(value)
            for _, values, _ in series
            for value in values
            if value is not None
        ),
    )
    return _three_series_svg("Actual grid power (+ import)", series, -maximum, maximum)


def _three_series_svg(
    title: str,
    series: tuple[tuple[str, tuple[float | None, ...], str], ...],
    minimum: float,
    maximum: float,
) -> str:
    """Render deterministic three-series SVG evidence without chart dependencies."""

    width, height = 960, 320
    left, right, top, bottom = 60.0, 930.0, 40.0, 250.0
    span = maximum - minimum
    if span <= 0:
        raise ValueError("comparison SVG range must be positive")

    def points(values: tuple[float | None, ...]) -> str:
        return " ".join(
            f"{left + (right - left) * index / (len(values) - 1):.2f},"
            f"{bottom - (value - minimum) * (bottom - top) / span:.2f}"
            for index, value in enumerate(values)
            if value is not None
        )

    legend = "".join(
        f'<text x="{60 + index * 260}" y="285" font-family="sans-serif" '
        f'font-size="12" fill="{color}">{name}</text>'
        for index, (name, _, color) in enumerate(series)
    )
    polylines = "".join(
        f'<polyline data-series="{name.lower()}" fill="none" stroke="{color}" '
        f'stroke-width="2" points="{points(values)}"/>'
        for name, values, color in series
    )
    zero_y = bottom - (0.0 - minimum) * (bottom - top) / span
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">'
        '<rect width="100%" height="100%" fill="white"/>'
        f'<text x="60" y="20" font-family="sans-serif" font-size="16">{title}</text>'
        f'<line x1="{left:.2f}" y1="{zero_y:.2f}" x2="{right:.2f}" '
        f'y2="{zero_y:.2f}" stroke="#64748b" stroke-width="1"/>'
        f"{polylines}{legend}</svg>\n"
    )


def _summary_text(
    full_result: HeadroomAwareExplainableMPCDailySimulationResult,
    rolling_result: RollingHeadroomAwareExplainableMPCDailySimulationResult,
    schedule_result: MultiOpportunityExplainableMPCDailySimulationResult,
    full: ComparisonMetrics,
    rolling: ComparisonMetrics,
    schedule: ComparisonMetrics,
    full_pv: PVAbsorptionMetrics,
    rolling_pv: PVAbsorptionMetrics,
    schedule_pv: PVAbsorptionMetrics,
    schedule_evidence: ScheduleEvidenceMetrics,
) -> str:
    early_full = full_result.step_traces[
        0
    ].headroom_mpc_cycle_result.headroom_optimization_output
    early_rolling = rolling_result.step_traces[
        0
    ].rolling_headroom_mpc_cycle_result.rolling_headroom_optimization_output
    early_schedule = schedule_result.step_traces[
        0
    ].multi_opportunity_mpc_cycle_result.multi_opportunity_optimization_output
    entry = early_schedule.headroom_schedule.entries[0]
    return (
        "EOS Full vs Rolling vs Schedule-Aware Headroom Comparison\n"
        "scenario=TASK-146 finite non-repeating 24-hour two-opportunity day\n"
        "opportunity_1=08:00-10:00; non_surplus_gap=11:00-13:00; "
        "opportunity_2=14:00-17:00\n"
        f"gap_tolerance_points={_GAP_TOLERANCE_POINTS}\n"
        "Schedule-aware is not assumed to be optimal; this demo reports "
        "observed behavior.\n"
        "early_00_reservation_comparison\n"
        + _early_full_text(early_full)
        + _early_rolling_text(early_rolling)
        + _early_schedule_text(early_schedule, entry)
        + "full\n"
        + _metrics_text(full, full_pv)
        + "rolling\n"
        + _metrics_text(rolling, rolling_pv)
        + "schedule_aware\n"
        + _metrics_text(schedule, schedule_pv)
        + _schedule_evidence_text(schedule_evidence)
        + "deltas_rolling_minus_full\n"
        + _delta_text(rolling, full, rolling_pv, full_pv)
        + "deltas_schedule_minus_full\n"
        + _delta_text(schedule, full, schedule_pv, full_pv)
        + "deltas_schedule_minus_rolling\n"
        + _delta_text(schedule, rolling, schedule_pv, rolling_pv)
        + "interpretation\n"
        + "Accounting effect: compare headroom and target evidence before any "
        "execution.\n"
        + "Reservation effect: compare requested and allowed cheap-grid charge "
        "at 00:00.\n"
        + "Control effect: compare actual SOC, grid power, and absorbed PV surplus.\n"
    )


def _early_full_text(output: HeadroomAwarePhysicalOptimizationSolveOutput) -> str:
    requirement = output.headroom_requirement
    reservation = output.candidate_planning_result.grid_charge_reservation
    requested = _reservation_value(reservation, "requested_grid_charge_power_kw")
    allowed = _reservation_value(reservation, "allowed_grid_charge_power_kw")
    return (
        f"full_required_headroom_kwh={requirement.required_headroom_energy_kwh:.6f}\n"
        f"full_target_soc={requirement.recommended_pre_pv_max_soc_fraction:.6f}\n"
        f"full_requested_grid_charge_kw={requested}\n"
        f"full_allowed_grid_charge_kw={allowed}\n"
    )


def _early_rolling_text(
    output: RollingHeadroomAwarePhysicalOptimizationSolveOutput,
) -> str:
    requirement = output.rolling_headroom_requirement
    reservation = output.candidate_planning_result.grid_charge_reservation
    start = _rolling_window_value(requirement, "start")
    end = _rolling_window_value(requirement, "end")
    requested = _reservation_value(reservation, "requested_grid_charge_power_kw")
    allowed = _reservation_value(reservation, "allowed_grid_charge_power_kw")
    return (
        f"rolling_first_opportunity_start={start}\n"
        f"rolling_first_opportunity_end={end}\n"
        f"rolling_required_headroom_kwh={requirement.headroom_requirement.required_headroom_energy_kwh:.6f}\n"
        f"rolling_target_soc={requirement.headroom_requirement.recommended_pre_pv_max_soc_fraction:.6f}\n"
        f"rolling_requested_grid_charge_kw={requested}\n"
        f"rolling_allowed_grid_charge_kw={allowed}\n"
    )


def _early_schedule_text(
    output: MultiOpportunityPhysicalOptimizationSolveOutput,
    entry: MultiOpportunityHeadroomScheduleEntry,
) -> str:
    reservation = output.candidate_planning_result.reservation_result
    requested = _reservation_value(reservation, "requested_grid_charge_power_kw")
    allowed = _reservation_value(reservation, "allowed_grid_charge_power_kw")
    return (
        f"schedule_opportunity_count={len(output.headroom_schedule.entries)}\n"
        "schedule_first_standalone_headroom_kwh="
        f"{entry.headroom_requirement.required_headroom_energy_kwh:.6f}\n"
        "schedule_first_adjusted_headroom_kwh="
        f"{entry.required_pre_opportunity_headroom_kwh:.6f}\n"
        f"schedule_gap_load_energy_kwh={entry.gap_net_deficit_load_energy_kwh:.6f}\n"
        "schedule_stored_depletion_potential_kwh="
        f"{entry.battery_stored_energy_depletion_potential_kwh:.6f}\n"
        "schedule_target_soc="
        f"{entry.recommended_pre_opportunity_max_soc_fraction:.6f}\n"
        f"schedule_requested_grid_charge_kw={requested}\n"
        f"schedule_allowed_grid_charge_kw={allowed}\n"
    )


def _metrics_text(metrics: ComparisonMetrics, pv: PVAbsorptionMetrics) -> str:
    return "".join(
        f"{name}={value}\n"
        for name, value in (
            ("pv_energy_kwh", _number(metrics.pv_energy_kwh)),
            ("load_energy_kwh", _number(metrics.load_energy_kwh)),
            ("battery_throughput_kwh", _number(metrics.battery_throughput_kwh)),
            ("grid_import_energy_kwh", _number(metrics.grid_import_energy_kwh)),
            ("grid_export_energy_kwh", _number(metrics.grid_export_energy_kwh)),
            ("final_soc", _number(metrics.final_soc)),
            ("charge_decisions", metrics.charge_decisions),
            ("discharge_decisions", metrics.discharge_decisions),
            ("idle_decisions", metrics.idle_decisions),
            ("revised_decisions", metrics.revised_decisions),
            ("soc_limited_decisions", metrics.soc_limited_decisions),
            ("power_limited_decisions", metrics.power_limited_decisions),
            ("reservation_count", metrics.reservation_count),
            ("reduced_reservation_count", metrics.reduced_reservation_count),
            ("zeroed_reservation_count", metrics.zeroed_reservation_count),
            ("minimum_target_soc", _number(metrics.minimum_target_soc)),
            (
                "maximum_required_headroom_kwh",
                _number(metrics.maximum_required_headroom_kwh),
            ),
            ("total_pv_surplus_energy_kwh", _number(pv.total_pv_surplus_energy_kwh)),
            (
                "estimated_absorbed_pv_surplus_energy_kwh",
                _number(pv.estimated_absorbed_pv_surplus_energy_kwh),
            ),
        )
    )


def _schedule_evidence_text(metrics: ScheduleEvidenceMetrics) -> str:
    return (
        "schedule_evidence\n"
        f"maximum_opportunity_entries={metrics.maximum_opportunity_entries}\n"
        f"no_opportunity_cycle_count={metrics.no_opportunity_cycle_count}\n"
        "minimum_first_standalone_headroom_kwh="
        f"{_optional_number(metrics.minimum_first_standalone_headroom_kwh)}\n"
        "maximum_first_standalone_headroom_kwh="
        f"{_optional_number(metrics.maximum_first_standalone_headroom_kwh)}\n"
        "minimum_first_adjusted_headroom_kwh="
        f"{_optional_number(metrics.minimum_first_adjusted_headroom_kwh)}\n"
        "maximum_first_adjusted_headroom_kwh="
        f"{_optional_number(metrics.maximum_first_adjusted_headroom_kwh)}\n"
        "maximum_stored_depletion_potential_kwh="
        f"{_number(metrics.maximum_stored_depletion_potential_kwh)}\n"
    )


def _delta_text(
    observed: ComparisonMetrics,
    reference: ComparisonMetrics,
    observed_pv: PVAbsorptionMetrics,
    reference_pv: PVAbsorptionMetrics,
) -> str:
    import_delta = observed.grid_import_energy_kwh - reference.grid_import_energy_kwh
    export_delta = observed.grid_export_energy_kwh - reference.grid_export_energy_kwh
    absorbed_delta = (
        observed_pv.estimated_absorbed_pv_surplus_energy_kwh
        - reference_pv.estimated_absorbed_pv_surplus_energy_kwh
    )
    return (
        f"grid_import_energy_kwh={import_delta:.6f}\n"
        f"grid_export_energy_kwh={export_delta:.6f}\n"
        f"final_soc={observed.final_soc - reference.final_soc:.6f}\n"
        "estimated_absorbed_pv_surplus_energy_kwh="
        f"{absorbed_delta:.6f}\n"
    )


def _pv_absorption(result: _DailyComparisonResult) -> PVAbsorptionMetrics:
    available = 0.0
    absorbed = 0.0
    for trace in result.simulation_result.traces:
        duration = trace.simulation_input.step_identity.duration_seconds / 3600.0
        pv = trace.state.pv_result.actual_power_kw
        load = trace.state.load_result.actual_power_kw
        surplus = max(pv - load, 0.0)
        available += surplus * duration
        absorbed += (
            min(max(trace.state.battery_result.actual_power_kw, 0.0), surplus)
            * duration
        )
    return PVAbsorptionMetrics(available, absorbed)


def _full_targets(
    result: HeadroomAwareExplainableMPCDailySimulationResult,
) -> tuple[float, ...]:
    return tuple(
        trace.headroom_mpc_cycle_result.headroom_optimization_output.headroom_requirement.recommended_pre_pv_max_soc_fraction
        for trace in result.step_traces
    )


def _rolling_targets(
    result: RollingHeadroomAwareExplainableMPCDailySimulationResult,
) -> tuple[float, ...]:
    return tuple(
        trace.rolling_headroom_mpc_cycle_result.rolling_headroom_optimization_output.rolling_headroom_requirement.headroom_requirement.recommended_pre_pv_max_soc_fraction
        for trace in result.step_traces
    )


def _schedule_targets(
    result: MultiOpportunityExplainableMPCDailySimulationResult,
) -> tuple[float | None, ...]:
    return tuple(
        output.headroom_schedule.entries[0].recommended_pre_opportunity_max_soc_fraction
        if output.headroom_schedule.entries
        else None
        for output in (
            trace.multi_opportunity_mpc_cycle_result.multi_opportunity_optimization_output
            for trace in result.step_traces
        )
    )


def _full_headrooms(
    result: HeadroomAwareExplainableMPCDailySimulationResult,
) -> tuple[float, ...]:
    return tuple(
        trace.headroom_mpc_cycle_result.headroom_optimization_output.headroom_requirement.required_headroom_energy_kwh
        for trace in result.step_traces
    )


def _rolling_headrooms(
    result: RollingHeadroomAwareExplainableMPCDailySimulationResult,
) -> tuple[float, ...]:
    return tuple(
        trace.rolling_headroom_mpc_cycle_result.rolling_headroom_optimization_output.rolling_headroom_requirement.headroom_requirement.required_headroom_energy_kwh
        for trace in result.step_traces
    )


def _schedule_headrooms(
    result: MultiOpportunityExplainableMPCDailySimulationResult,
) -> tuple[float | None, ...]:
    return tuple(
        output.headroom_schedule.entries[0].required_pre_opportunity_headroom_kwh
        if output.headroom_schedule.entries
        else None
        for output in (
            trace.multi_opportunity_mpc_cycle_result.multi_opportunity_optimization_output
            for trace in result.step_traces
        )
    )


def _next_socs(result: _DailyComparisonResult) -> tuple[float, ...]:
    return tuple(
        trace.simulation_trace.state.battery_result.next_state.soc
        for trace in result.step_traces
    )


def _grid_values(result: _DailyComparisonResult) -> tuple[float, ...]:
    return tuple(
        trace.simulation_trace.state.grid_result.actual_grid_power_kw
        for trace in result.step_traces
    )


def _rolling_window_value(
    requirement: RollingPVHeadroomRequirement,
    value: str,
) -> str:
    steps = requirement.opportunity_window.steps
    if not steps:
        return ""
    point = steps[0] if value == "start" else steps[-1]
    return point.forecast_point.timestamp.isoformat()


def _entry_window_value(
    entry: MultiOpportunityHeadroomScheduleEntry | None,
    value: str,
) -> str:
    if entry is None:
        return ""
    selected = entry.opportunity.selected_forecast_horizon.points
    point = selected[0] if value == "start" else selected[-1]
    return point.timestamp.isoformat()


def _entry_value(
    entry: MultiOpportunityHeadroomScheduleEntry | None,
    field_name: str,
) -> str:
    if entry is None:
        return ""
    values = {
        "headroom_requirement.required_headroom_energy_kwh": (
            entry.headroom_requirement.required_headroom_energy_kwh
        ),
        "required_pre_opportunity_headroom_kwh": (
            entry.required_pre_opportunity_headroom_kwh
        ),
        "recommended_pre_opportunity_max_soc_fraction": (
            entry.recommended_pre_opportunity_max_soc_fraction
        ),
        "gap_net_deficit_load_energy_kwh": entry.gap_net_deficit_load_energy_kwh,
        "battery_stored_energy_depletion_potential_kwh": (
            entry.battery_stored_energy_depletion_potential_kwh
        ),
    }
    value = values.get(field_name)
    if value is None:
        raise ValueError(f"unsupported schedule entry field: {field_name}")
    return _number(value)


def _reservation_value(
    reservation: _GridChargeReservationEvidence | None,
    field_name: str,
) -> str:
    if reservation is None:
        return ""
    if field_name == "requested_grid_charge_power_kw":
        return _number(reservation.requested_grid_charge_power_kw)
    if field_name == "allowed_grid_charge_power_kw":
        return _number(reservation.allowed_grid_charge_power_kw)
    raise ValueError(f"unsupported reservation field: {field_name}")


def _reservation_applied(reservation: _GridChargeReservationEvidence) -> bool:
    return reservation.reservation_applied


def _reservation_allowed(reservation: _GridChargeReservationEvidence) -> float:
    return reservation.allowed_grid_charge_power_kw


def _number(value: float) -> str:
    return f"{value:.6f}"


def _optional_number(value: float | None) -> str:
    return "" if value is None else _number(value)


if __name__ == "__main__":
    raise SystemExit(main())
