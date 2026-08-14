"""Compare the existing full and rolling headroom-aware MPC daily paths.

This module is an observation-only demo.  It composes the frozen TASK-138
full-horizon runner and TASK-144 rolling-opportunity runner with the same
caller-owned TASK-139 scenario and 24-point repeating forecast horizons.  It
does not alter either optimizer, physical revision, feasibility, actuation, or
simulator behavior.
"""

import argparse
import csv
from collections.abc import Sequence
from dataclasses import dataclass, replace
from io import StringIO
from pathlib import Path

from ems_simulator.explainable_mpc_daily import ExplainableMPCDailySimulationInput
from ems_simulator.headroom_aware_explainable_mpc_daily import (
    HeadroomAwareExplainableMPCDailySimulationResult,
)
from ems_simulator.headroom_aware_mpc_demo import _runner as _full_runner
from ems_simulator.headroom_aware_mpc_demo import create_demo_input
from ems_simulator.net_load_mpc_demo import (
    _DemoMPCDecisionTranslator,
    _DemoPassThroughFeasibility,
    _DemoSimulationHandoff,
)
from ems_simulator.output import DailyEnergySummary, SimulationResultExporter
from ems_simulator.rolling_headroom_aware_explainable_mpc_daily import (
    RollingHeadroomAwareExplainableMPCDailySimulationResult,
    RollingHeadroomAwareExplainableMPCDailySimulationRunner,
)
from ems_strategy import (
    DeterministicExplainableMPCDecisionCSVFileExporter,
    DeterministicExplainableMPCDecisionCSVRowMapper,
    DeterministicExplainableMPCDecisionCSVSerializer,
    DeterministicExplainableMPCDecisionJournalRecordBuilder,
    DeterministicMPCDecisionExplanationBuilder,
    DeterministicMPCDecisionExplanationFormatter,
    ExplainableMPCDecisionJournalRecord,
    FirstStepMPCCurrentActionExtractor,
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
    HeadroomAwareGridChargeReservation,
    NetLoadAwareBaselineOptimizationConfiguration,
    NetLoadAwareBaselineOptimizer,
    OptimizationSolutionControlPlanBuilder,
    PVOpportunityWindowConfiguration,
)

_CSV_COLUMNS = (
    "timestamp",
    "actual_soc",
    "full_required_headroom_kwh",
    "full_recommended_max_soc",
    "full_requested_grid_charge_kw",
    "full_allowed_grid_charge_kw",
    "full_final_candidate_action",
    "full_final_candidate_power_kw",
    "full_final_physical_action",
    "full_final_physical_power_kw",
    "rolling_opportunity_start",
    "rolling_opportunity_end",
    "rolling_opportunity_indexes",
    "rolling_required_headroom_kwh",
    "rolling_recommended_max_soc",
    "rolling_requested_grid_charge_kw",
    "rolling_allowed_grid_charge_kw",
    "rolling_final_candidate_action",
    "rolling_final_candidate_power_kw",
    "rolling_final_physical_action",
    "rolling_final_physical_power_kw",
    "full_actual_battery_power_kw",
    "rolling_actual_battery_power_kw",
    "full_actual_grid_power_kw",
    "rolling_actual_grid_power_kw",
    "full_next_soc",
    "rolling_next_soc",
)


@dataclass(frozen=True, slots=True)
class HeadroomComparisonMetrics:
    """Aggregate measured daily behavior for one existing runner path."""

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
    minimum_recommended_max_soc: float
    maximum_required_headroom_kwh: float
    no_opportunity_cycles: int = 0
    distinct_opportunity_windows: int = 0


@dataclass(frozen=True, slots=True)
class RollingHeadroomMPCDemoExecutionResult:
    """Retain completed comparison evidence and all caller-targeted outputs."""

    full_source_input: ExplainableMPCDailySimulationInput
    rolling_source_input: ExplainableMPCDailySimulationInput
    full_result: HeadroomAwareExplainableMPCDailySimulationResult
    rolling_result: RollingHeadroomAwareExplainableMPCDailySimulationResult
    full_metrics: HeadroomComparisonMetrics
    rolling_metrics: HeadroomComparisonMetrics
    comparison_csv_path: Path
    summary_path: Path
    target_svg_path: Path
    soc_svg_path: Path
    grid_svg_path: Path


def run_demo(output_directory: Path) -> RollingHeadroomMPCDemoExecutionResult:
    """Run one deterministic A/B comparison and export only observed evidence."""

    if not isinstance(output_directory, Path):
        raise TypeError("output_directory must be a pathlib.Path")
    output_directory.mkdir(parents=True, exist_ok=True)

    full_source = create_demo_input(output_directory)
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
    full_source = ExplainableMPCDailySimulationInput(
        full_source.integration_input,
        full_source.forecast_horizons,
        full_source.mpc_configuration,
        full_source.optimization_objectives,
        full_source.source_strategy,
        full_source.battery_optimization_model,
        full_source.explanation_locale,
        output_directory / "full_mpc_decisions.csv",
    )

    full_result = _full_runner().run(full_source)
    rolling_result = _rolling_runner().run(rolling_source)
    full_metrics = _full_metrics(full_result)
    rolling_metrics = _rolling_metrics(rolling_result)

    comparison_csv_path = output_directory / "headroom_comparison.csv"
    comparison_csv_path.write_text(
        _comparison_csv(full_result, rolling_result), encoding="utf-8", newline=""
    )
    target_svg_path = output_directory / "recommended_soc_target.svg"
    soc_svg_path = output_directory / "soc_comparison.svg"
    grid_svg_path = output_directory / "grid_power_comparison.svg"
    target_svg_path.write_text(
        _target_svg(full_result, rolling_result), encoding="utf-8", newline=""
    )
    soc_svg_path.write_text(
        _soc_svg(full_result, rolling_result), encoding="utf-8", newline=""
    )
    grid_svg_path.write_text(
        _grid_svg(full_result, rolling_result), encoding="utf-8", newline=""
    )
    summary_path = output_directory / "daily_summary.txt"
    summary_path.write_text(
        _summary_text(full_metrics, rolling_metrics), encoding="utf-8", newline=""
    )
    return RollingHeadroomMPCDemoExecutionResult(
        full_source,
        rolling_source,
        full_result,
        rolling_result,
        full_metrics,
        rolling_metrics,
        comparison_csv_path,
        summary_path,
        target_svg_path,
        soc_svg_path,
        grid_svg_path,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the finite full-versus-rolling headroom comparison CLI."""

    parser = argparse.ArgumentParser(
        description="EOS full versus rolling headroom-aware MPC comparison"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("simulation_output_rolling_headroom_comparison"),
        help="directory for deterministic comparison evidence",
    )
    arguments = parser.parse_args(argv)
    execution = run_demo(arguments.output_dir)
    for path in (
        execution.comparison_csv_path,
        execution.summary_path,
        execution.target_svg_path,
        execution.soc_svg_path,
        execution.grid_svg_path,
    ):
        print(path)
    return 0


def _rolling_runner() -> RollingHeadroomAwareExplainableMPCDailySimulationRunner:
    """Compose only the existing TASK-140 to TASK-144 rolling path."""

    optimizer = DeterministicRollingHeadroomAwarePhysicalOptimizer(
        DeterministicRollingPVHeadroomRequirementCalculator(
            DeterministicPVOpportunityWindowSelector(),
            DeterministicPVHeadroomRequirementCalculator(),
        ),
        DeterministicHeadroomAwareCandidatePlanner(
            NetLoadAwareBaselineOptimizer(
                NetLoadAwareBaselineOptimizationConfiguration(0.30, 0.90, 3.0)
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
    cycle = RollingHeadroomAwareSingleMPCCycleOrchestrator(
        optimizer,
        OptimizationSolutionControlPlanBuilder(),
        FirstStepMPCCurrentActionExtractor(),
        _DemoMPCDecisionTranslator(),
    )
    return RollingHeadroomAwareExplainableMPCDailySimulationRunner(
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
) -> HeadroomComparisonMetrics:
    requirements = tuple(
        trace.headroom_mpc_cycle_result.headroom_optimization_output.headroom_requirement
        for trace in result.step_traces
    )
    reservations = tuple(
        output.candidate_planning_result.grid_charge_reservation
        for output in (
            trace.headroom_mpc_cycle_result.headroom_optimization_output
            for trace in result.step_traces
        )
        if output.candidate_planning_result.grid_charge_reservation is not None
    )
    return _metrics_from_records(
        SimulationResultExporter.export(result.simulation_result).summary,
        result.journal_records,
        tuple(reservation for reservation in reservations if reservation is not None),
        tuple(
            requirement.recommended_pre_pv_max_soc_fraction
            for requirement in requirements
        ),
        tuple(requirement.required_headroom_energy_kwh for requirement in requirements),
    )


def _rolling_metrics(
    result: RollingHeadroomAwareExplainableMPCDailySimulationResult,
) -> HeadroomComparisonMetrics:
    requirements = tuple(
        trace.rolling_headroom_mpc_cycle_result.rolling_headroom_optimization_output.rolling_headroom_requirement.headroom_requirement
        for trace in result.step_traces
    )
    windows = tuple(
        trace.rolling_headroom_mpc_cycle_result.rolling_headroom_optimization_output.rolling_headroom_requirement.opportunity_window
        for trace in result.step_traces
    )
    reservations = tuple(
        output.candidate_planning_result.grid_charge_reservation
        for output in (
            trace.rolling_headroom_mpc_cycle_result.rolling_headroom_optimization_output
            for trace in result.step_traces
        )
        if output.candidate_planning_result.grid_charge_reservation is not None
    )
    metrics = _metrics_from_records(
        SimulationResultExporter.export(result.simulation_result).summary,
        result.journal_records,
        tuple(reservation for reservation in reservations if reservation is not None),
        tuple(
            requirement.recommended_pre_pv_max_soc_fraction
            for requirement in requirements
        ),
        tuple(requirement.required_headroom_energy_kwh for requirement in requirements),
    )
    signatures = {
        (window.start_index, window.end_index_exclusive)
        for window in windows
        if window.steps
    }
    return replace(
        metrics,
        no_opportunity_cycles=sum(not window.steps for window in windows),
        distinct_opportunity_windows=len(signatures),
    )


def _metrics_from_records(
    summary: DailyEnergySummary,
    records: tuple[ExplainableMPCDecisionJournalRecord, ...],
    reservations: tuple[HeadroomAwareGridChargeReservation, ...],
    targets: tuple[float, ...],
    headrooms: tuple[float, ...],
) -> HeadroomComparisonMetrics:
    reasons = tuple(reason for record in records for reason in record.revision_reasons)
    final_soc = summary.source_result.traces[-1].state.battery_result.next_state.soc
    return HeadroomComparisonMetrics(
        summary.pv_energy_kwh,
        summary.load_energy_kwh,
        summary.battery_throughput_kwh,
        summary.grid_import_energy_kwh,
        summary.grid_export_energy_kwh,
        final_soc,
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
        sum(reservation.reservation_applied for reservation in reservations),
        sum(
            reservation.allowed_grid_charge_power_kw == 0
            for reservation in reservations
        ),
        min(targets),
        max(headrooms),
    )


def _comparison_csv(
    full: HeadroomAwareExplainableMPCDailySimulationResult,
    rolling: RollingHeadroomAwareExplainableMPCDailySimulationResult,
) -> str:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(_CSV_COLUMNS)
    for full_trace, rolling_trace in zip(
        full.step_traces, rolling.step_traces, strict=True
    ):
        full_output = full_trace.headroom_mpc_cycle_result.headroom_optimization_output
        rolling_cycle = rolling_trace.rolling_headroom_mpc_cycle_result
        rolling_output = rolling_cycle.rolling_headroom_optimization_output
        full_requirement = full_output.headroom_requirement
        rolling_requirement = rolling_output.rolling_headroom_requirement
        full_reservation = full_output.candidate_planning_result.grid_charge_reservation
        rolling_reservation = (
            rolling_output.candidate_planning_result.grid_charge_reservation
        )
        full_candidate = (
            full_output.candidate_planning_result.final_output.solution.steps[0]
        )
        rolling_candidate = (
            rolling_output.candidate_planning_result.final_output.solution.steps[0]
        )
        full_physical = full_output.physical_output.final_output.solution.steps[0]
        rolling_physical = rolling_output.physical_output.final_output.solution.steps[0]
        window = rolling_requirement.opportunity_window
        timestamp = full_trace.simulation_trace.simulation_input.step_identity.timestamp
        if timestamp is None:
            raise ValueError("comparison requires explicit step timestamps")
        start = (
            ""
            if not window.steps
            else window.steps[0].forecast_point.timestamp.isoformat()
        )
        end = (
            ""
            if not window.steps
            else window.steps[-1].forecast_point.timestamp.isoformat()
        )
        writer.writerow(
            (
                timestamp.isoformat(),
                _number(
                    full_trace.headroom_mpc_cycle_result.source_input.battery_state.soc_fraction
                ),
                _number(full_requirement.required_headroom_energy_kwh),
                _number(full_requirement.recommended_pre_pv_max_soc_fraction),
                _reservation_value(full_reservation, "requested_grid_charge_power_kw"),
                _reservation_value(full_reservation, "allowed_grid_charge_power_kw"),
                full_candidate.intent.action,
                _number(full_candidate.requested_power_kw),
                full_physical.intent.action,
                _number(full_physical.requested_power_kw),
                start,
                end,
                ""
                if not window.steps
                else "|".join(str(step.source_index) for step in window.steps),
                _number(
                    rolling_requirement.headroom_requirement.required_headroom_energy_kwh
                ),
                _number(
                    rolling_requirement.headroom_requirement.recommended_pre_pv_max_soc_fraction
                ),
                _reservation_value(
                    rolling_reservation, "requested_grid_charge_power_kw"
                ),
                _reservation_value(rolling_reservation, "allowed_grid_charge_power_kw"),
                rolling_candidate.intent.action,
                _number(rolling_candidate.requested_power_kw),
                rolling_physical.intent.action,
                _number(rolling_physical.requested_power_kw),
                _number(
                    full_trace.simulation_trace.state.battery_result.actual_power_kw
                ),
                _number(
                    rolling_trace.simulation_trace.state.battery_result.actual_power_kw
                ),
                _number(
                    full_trace.simulation_trace.state.grid_result.actual_grid_power_kw
                ),
                _number(
                    rolling_trace.simulation_trace.state.grid_result.actual_grid_power_kw
                ),
                _number(
                    full_trace.simulation_trace.state.battery_result.next_state.soc
                ),
                _number(
                    rolling_trace.simulation_trace.state.battery_result.next_state.soc
                ),
            )
        )
    return stream.getvalue()


def _reservation_value(reservation: object | None, field_name: str) -> str:
    if reservation is None:
        return ""
    value = getattr(reservation, field_name)
    if not isinstance(value, float):
        raise TypeError(f"reservation {field_name} must be a float")
    return _number(value)


def _number(value: float) -> str:
    return f"{value:.6f}"


def _target_svg(
    full: HeadroomAwareExplainableMPCDailySimulationResult,
    rolling: RollingHeadroomAwareExplainableMPCDailySimulationResult,
) -> str:
    return _two_series_svg(
        "Recommended pre-PV maximum SOC",
        "Full horizon target",
        tuple(
            trace.headroom_mpc_cycle_result.headroom_optimization_output.headroom_requirement.recommended_pre_pv_max_soc_fraction
            for trace in full.step_traces
        ),
        "Rolling opportunity target",
        tuple(
            trace.rolling_headroom_mpc_cycle_result.rolling_headroom_optimization_output.rolling_headroom_requirement.headroom_requirement.recommended_pre_pv_max_soc_fraction
            for trace in rolling.step_traces
        ),
        0.0,
        1.0,
    )


def _soc_svg(
    full: HeadroomAwareExplainableMPCDailySimulationResult,
    rolling: RollingHeadroomAwareExplainableMPCDailySimulationResult,
) -> str:
    return _two_series_svg(
        "Actual SOC comparison",
        "Full horizon actual SOC",
        tuple(
            trace.simulation_trace.state.battery_result.next_state.soc
            for trace in full.step_traces
        ),
        "Rolling opportunity actual SOC",
        tuple(
            trace.simulation_trace.state.battery_result.next_state.soc
            for trace in rolling.step_traces
        ),
        0.0,
        1.0,
    )


def _grid_svg(
    full: HeadroomAwareExplainableMPCDailySimulationResult,
    rolling: RollingHeadroomAwareExplainableMPCDailySimulationResult,
) -> str:
    full_grid = tuple(
        trace.simulation_trace.state.grid_result.actual_grid_power_kw
        for trace in full.step_traces
    )
    rolling_grid = tuple(
        trace.simulation_trace.state.grid_result.actual_grid_power_kw
        for trace in rolling.step_traces
    )
    maximum = max(1.0, *(abs(value) for value in (*full_grid, *rolling_grid)))
    return _two_series_svg(
        "Actual grid power comparison (positive = import)",
        "Full horizon grid",
        full_grid,
        "Rolling opportunity grid",
        rolling_grid,
        -maximum,
        maximum,
    )


def _two_series_svg(
    title: str,
    first_name: str,
    first: tuple[float, ...],
    second_name: str,
    second: tuple[float, ...],
    minimum: float,
    maximum: float,
) -> str:
    """Use the existing simple stdlib SVG convention for comparison curves."""

    width, height = 960, 300
    left, right, top, bottom = 60.0, 930.0, 40.0, 250.0
    span = maximum - minimum
    if span <= 0:
        raise ValueError("comparison SVG range must be positive")

    def points(values: tuple[float, ...]) -> str:
        return " ".join(
            f"{left + (right - left) * index / (len(values) - 1):.2f},"
            f"{bottom - (value - minimum) * (bottom - top) / span:.2f}"
            for index, value in enumerate(values)
        )

    first_points = points(first)
    second_points = points(second)
    zero_y = bottom - (0.0 - minimum) * (bottom - top) / span
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">'
        '<rect width="100%" height="100%" fill="white"/>'
        f'<text x="60" y="20" font-family="sans-serif" font-size="16">{title}</text>'
        f'<text x="60" y="285" font-family="sans-serif" font-size="12" '
        f'fill="#2563eb">{first_name}</text>'
        f'<text x="360" y="285" font-family="sans-serif" font-size="12" '
        f'fill="#dc2626">{second_name}</text>'
        f'<line x1="{left:.2f}" y1="{zero_y:.2f}" x2="{right:.2f}" '
        f'y2="{zero_y:.2f}" stroke="#64748b" stroke-width="1"/>'
        f'<polyline data-series="full" fill="none" stroke="#2563eb" '
        f'stroke-width="2" points="{first_points}"/>'
        f'<polyline data-series="rolling" fill="none" stroke="#dc2626" '
        f'stroke-width="2" points="{second_points}"/>'
        "</svg>\n"
    )


def _summary_text(
    full: HeadroomComparisonMetrics,
    rolling: HeadroomComparisonMetrics,
) -> str:
    """Render measured metrics without asserting either path is universally better."""

    return (
        "EOS Full vs Rolling Headroom MPC Comparison\n"
        "full_horizon\n"
        + _metrics_text(full)
        + "rolling_opportunity\n"
        + _metrics_text(rolling)
        + "deltas_rolling_minus_full\n"
        + "grid_import_energy_kwh="
        + f"{rolling.grid_import_energy_kwh - full.grid_import_energy_kwh:.6f}\n"
        + "grid_export_energy_kwh="
        + f"{rolling.grid_export_energy_kwh - full.grid_export_energy_kwh:.6f}\n"
        + f"final_soc={rolling.final_soc - full.final_soc:.6f}\n"
        + "interpretation\n"
        + "Rolling is not automatically better; this demo reports observed behavior.\n"
        + "The comparison retains full-horizon and rolling-opportunity provenance "
        + "separately.\n"
    )


def _metrics_text(metrics: HeadroomComparisonMetrics) -> str:
    return (
        f"pv_energy_kwh={metrics.pv_energy_kwh:.6f}\n"
        f"load_energy_kwh={metrics.load_energy_kwh:.6f}\n"
        f"battery_throughput_kwh={metrics.battery_throughput_kwh:.6f}\n"
        f"grid_import_energy_kwh={metrics.grid_import_energy_kwh:.6f}\n"
        f"grid_export_energy_kwh={metrics.grid_export_energy_kwh:.6f}\n"
        f"final_soc={metrics.final_soc:.6f}\n"
        f"charge_decisions={metrics.charge_decisions}\n"
        f"discharge_decisions={metrics.discharge_decisions}\n"
        f"idle_decisions={metrics.idle_decisions}\n"
        f"revised_decisions={metrics.revised_decisions}\n"
        f"soc_limited_decisions={metrics.soc_limited_decisions}\n"
        f"power_limited_decisions={metrics.power_limited_decisions}\n"
        f"headroom_reservations={metrics.reservation_count}\n"
        f"headroom_reduced_reservations={metrics.reduced_reservation_count}\n"
        f"headroom_zeroed_reservations={metrics.zeroed_reservation_count}\n"
        f"minimum_recommended_max_soc={metrics.minimum_recommended_max_soc:.6f}\n"
        f"maximum_required_headroom_kwh={metrics.maximum_required_headroom_kwh:.6f}\n"
        f"no_opportunity_cycles={metrics.no_opportunity_cycles}\n"
        f"distinct_opportunity_windows={metrics.distinct_opportunity_windows}\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
