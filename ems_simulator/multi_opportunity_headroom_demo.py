"""Diagnostic full-versus-rolling headroom demo with two finite PV windows.

The demo is observational.  It composes the frozen TASK-138 full-horizon and
TASK-144 rolling-opportunity daily paths unchanged, then reads the exact outer
provenance retained by each path.  The forecasts are caller-owned, finite, and
never wrap the experimental day.
"""

import argparse
import csv
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path

from capability import (
    ActiveCapabilityCollection,
    AvailableCapabilityCollection,
    CapabilityDescriptor,
    CapabilityMatch,
    CapabilityMatchCollection,
    RequiredCapabilityCollection,
)
from ems_simulator.ems_integration import EMSIntegrationScenarioInput
from ems_simulator.explainable_mpc_daily import ExplainableMPCDailySimulationInput
from ems_simulator.headroom_aware_explainable_mpc_daily import (
    HeadroomAwareExplainableMPCDailySimulationResult,
)
from ems_simulator.headroom_aware_mpc_demo import _runner as _full_runner
from ems_simulator.input import BatteryParameters, DailySimulationScenarioInput
from ems_simulator.rolling_headroom_aware_explainable_mpc_daily import (
    RollingHeadroomAwareExplainableMPCDailySimulationResult,
)
from ems_simulator.rolling_headroom_mpc_demo import (
    HeadroomComparisonMetrics,
    _full_metrics,
    _rolling_metrics,
    _rolling_runner,
    _two_series_svg,
)
from ems_strategy import EMSStrategyDescriptor, MPCConfiguration
from forecast import ForecastHorizon, ForecastPoint
from objective import ObjectiveCapabilityActivationComposition, ObjectiveDescriptor
from optimization import (
    BatteryOptimizationModel,
    HeadroomAwarePhysicalOptimizationSolveOutput,
    OptimizationObjective,
    OptimizationObjectiveCollection,
    PVOpportunityWindow,
    PVOpportunityWindowStep,
    RollingHeadroomAwarePhysicalOptimizationSolveOutput,
)
from simulator import SimulationStepIdentity

_HOURS_PER_DAY = 24
_HORIZON_POINTS = 24
_START = datetime(2026, 2, 1, tzinfo=UTC)
_GAP_TOLERANCE_POINTS = 1

# Two deliberately separate PV-surplus opportunities: 08:00--10:00 and
# 14:00--17:00.  The three 11:00--13:00 points are all non-surplus.
PV_POWER_PROFILE_KW = (
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    2.0,
    2.5,
    2.0,
    0.4,
    0.2,
    0.1,
    3.0,
    4.0,
    3.5,
    2.5,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
)
LOAD_POWER_PROFILE_KW = (
    0.8,
    0.8,
    0.8,
    0.8,
    0.8,
    0.8,
    0.9,
    0.9,
    0.8,
    0.8,
    0.9,
    1.0,
    1.1,
    1.0,
    1.0,
    1.0,
    1.0,
    1.2,
    2.0,
    2.5,
    2.2,
    1.8,
    1.2,
    1.0,
)
TARIFF_PROFILE_CNY_PER_KWH = (
    0.20,
    0.20,
    0.20,
    0.20,
    0.20,
    0.20,
    0.50,
    0.50,
    0.50,
    0.50,
    0.50,
    0.50,
    0.50,
    0.50,
    0.60,
    0.60,
    0.60,
    0.60,
    0.90,
    0.90,
    0.90,
    0.90,
    0.50,
    0.50,
)

_CSV_COLUMNS = (
    "timestamp",
    "full_actual_soc",
    "rolling_actual_soc",
    "full_required_headroom_kwh",
    "rolling_required_headroom_kwh",
    "full_recommended_max_soc",
    "rolling_recommended_max_soc",
    "rolling_opportunity_start",
    "rolling_opportunity_end",
    "rolling_selected_source_indexes",
    "rolling_selected_point_count",
    "full_requested_grid_charge_kw",
    "rolling_requested_grid_charge_kw",
    "full_allowed_grid_charge_kw",
    "rolling_allowed_grid_charge_kw",
    "full_candidate_battery_power_kw",
    "rolling_candidate_battery_power_kw",
    "full_physical_battery_power_kw",
    "rolling_physical_battery_power_kw",
    "full_actual_battery_power_kw",
    "rolling_actual_battery_power_kw",
    "full_actual_grid_power_kw",
    "rolling_actual_grid_power_kw",
    "full_next_soc",
    "rolling_next_soc",
)


@dataclass(frozen=True, slots=True)
class PVAbsorptionMetrics:
    """Read-only PV-surplus accounting derived from actual simulation traces."""

    total_pv_surplus_energy_kwh: float
    estimated_absorbed_pv_surplus_energy_kwh: float


@dataclass(frozen=True, slots=True)
class MultiOpportunityHeadroomDemoExecutionResult:
    """Retain both completed paths and all output files for one experiment."""

    full_source_input: ExplainableMPCDailySimulationInput
    rolling_source_input: ExplainableMPCDailySimulationInput
    full_result: HeadroomAwareExplainableMPCDailySimulationResult
    rolling_result: RollingHeadroomAwareExplainableMPCDailySimulationResult
    full_metrics: HeadroomComparisonMetrics
    rolling_metrics: HeadroomComparisonMetrics
    full_pv_absorption: PVAbsorptionMetrics
    rolling_pv_absorption: PVAbsorptionMetrics
    comparison_csv_path: Path
    summary_path: Path
    target_svg_path: Path
    required_headroom_svg_path: Path
    soc_svg_path: Path
    grid_svg_path: Path


def create_demo_input(output_directory: Path) -> ExplainableMPCDailySimulationInput:
    """Create the deterministic finite-day facts and 24 caller-owned horizons."""

    if not isinstance(output_directory, Path):
        raise TypeError("output_directory must be a pathlib.Path")
    daily_input = _daily_input()
    capability = CapabilityDescriptor(
        "multi-opportunity-net-load-mpc",
        "Diagnostic finite-day net-load MPC facts.",
    )
    match_collection = CapabilityMatchCollection(
        RequiredCapabilityCollection((capability,)),
        AvailableCapabilityCollection((capability,)),
        (CapabilityMatch(capability, capability),),
        (),
    )
    active = ActiveCapabilityCollection(match_collection, (capability,), ())
    integration = EMSIntegrationScenarioInput(
        daily_input,
        ObjectiveCapabilityActivationComposition(
            ObjectiveDescriptor("energy_cost", "Minimize imported energy cost."),
            active,
        ),
        capability,
        3.0,
        5.0,
        0.0,
    )
    return ExplainableMPCDailySimulationInput(
        integration,
        _finite_horizons(daily_input),
        MPCConfiguration(_HORIZON_POINTS, 3600.0),
        OptimizationObjectiveCollection(
            (OptimizationObjective("energy_cost", "minimize"),)
        ),
        EMSStrategyDescriptor("multi-opportunity-net-load-mpc", "1.0"),
        BatteryOptimizationModel(10.0, 0.20, 1.0, 3.0, 3.0, 0.95, 0.95),
        "zh-CN",
        output_directory / "full_mpc_decisions.csv",
    )


def run_demo(output_directory: Path) -> MultiOpportunityHeadroomDemoExecutionResult:
    """Run both frozen daily paths using exactly the same experimental facts."""

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
    full_result = _full_runner().run(full_source)
    rolling_result = _rolling_runner().run(rolling_source)
    full_metrics = _full_metrics(full_result)
    rolling_metrics = _rolling_metrics(rolling_result)
    full_pv_absorption = _pv_absorption(full_result)
    rolling_pv_absorption = _pv_absorption(rolling_result)

    comparison_csv_path = output_directory / "multi_opportunity_headroom_comparison.csv"
    comparison_csv_path.write_text(
        _comparison_csv(full_result, rolling_result), encoding="utf-8", newline=""
    )
    target_svg_path = output_directory / "recommended_soc_target.svg"
    required_headroom_svg_path = output_directory / "required_headroom_comparison.svg"
    soc_svg_path = output_directory / "soc_comparison.svg"
    grid_svg_path = output_directory / "grid_power_comparison.svg"
    target_svg_path.write_text(
        _target_svg(full_result, rolling_result), encoding="utf-8", newline=""
    )
    required_headroom_svg_path.write_text(
        _required_headroom_svg(full_result, rolling_result),
        encoding="utf-8",
        newline="",
    )
    soc_svg_path.write_text(
        _soc_svg(full_result, rolling_result), encoding="utf-8", newline=""
    )
    grid_svg_path.write_text(
        _grid_svg(full_result, rolling_result), encoding="utf-8", newline=""
    )
    summary_path = output_directory / "daily_summary.txt"
    summary_path.write_text(
        _summary_text(
            full_result,
            rolling_result,
            full_metrics,
            rolling_metrics,
            full_pv_absorption,
            rolling_pv_absorption,
        ),
        encoding="utf-8",
        newline="",
    )
    return MultiOpportunityHeadroomDemoExecutionResult(
        full_source,
        rolling_source,
        full_result,
        rolling_result,
        full_metrics,
        rolling_metrics,
        full_pv_absorption,
        rolling_pv_absorption,
        comparison_csv_path,
        summary_path,
        target_svg_path,
        required_headroom_svg_path,
        soc_svg_path,
        grid_svg_path,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the finite multi-opportunity diagnostic comparison CLI."""

    parser = argparse.ArgumentParser(
        description="EOS multi-opportunity full versus rolling headroom validation"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("simulation_output_task146_multi_opportunity"),
        help="directory for deterministic multi-opportunity evidence",
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


def _daily_input() -> DailySimulationScenarioInput:
    identities = tuple(
        SimulationStepIdentity(hour, 3600.0, _START + timedelta(hours=hour))
        for hour in range(_HOURS_PER_DAY)
    )
    return DailySimulationScenarioInput(
        identities,
        PV_POWER_PROFILE_KW,
        LOAD_POWER_PROFILE_KW,
        TARIFF_PROFILE_CNY_PER_KWH,
        BatteryParameters(10.0, 3.0, 3.0, 0.95, 0.95, 0.20),
        0.50,
    )


def _finite_horizons(
    daily_input: DailySimulationScenarioInput,
) -> tuple[ForecastHorizon, ...]:
    """Build fixed-shape horizons from remaining day plus explicit zero tails.

    The zero tails are distinct caller facts after the experiment ends.  They
    are not a repeated day and cannot create a later PV opportunity.
    """

    horizons: list[ForecastHorizon] = []
    for hour, identity in enumerate(daily_input.step_identities):
        timestamp = identity.timestamp
        if timestamp is None:
            raise ValueError("demo step timestamps must be present")
        points = tuple(
            _forecast_point(hour + offset, timestamp + timedelta(hours=offset))
            for offset in range(_HORIZON_POINTS)
        )
        horizons.append(ForecastHorizon(points))
    return tuple(horizons)


def _forecast_point(index: int, timestamp: datetime) -> ForecastPoint:
    if index < _HOURS_PER_DAY:
        return ForecastPoint(
            timestamp,
            PV_POWER_PROFILE_KW[index],
            LOAD_POWER_PROFILE_KW[index],
            TARIFF_PROFILE_CNY_PER_KWH[index],
        )
    return ForecastPoint(timestamp, 0.0, 0.0, 0.50)


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
        window = rolling_requirement.opportunity_window
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
        timestamp = full_trace.simulation_trace.simulation_input.step_identity.timestamp
        if timestamp is None:
            raise ValueError("comparison requires explicit timestamps")
        start, end, indexes, count = _window_metadata(window.steps)
        writer.writerow(
            (
                timestamp.isoformat(),
                _number(
                    full_trace.headroom_mpc_cycle_result.source_input.battery_state.soc_fraction
                ),
                _number(rolling_cycle.source_input.battery_state.soc_fraction),
                _number(full_requirement.required_headroom_energy_kwh),
                _number(
                    rolling_requirement.headroom_requirement.required_headroom_energy_kwh
                ),
                _number(full_requirement.recommended_pre_pv_max_soc_fraction),
                _number(
                    rolling_requirement.headroom_requirement.recommended_pre_pv_max_soc_fraction
                ),
                start,
                end,
                indexes,
                count,
                _reservation_value(full_reservation, "requested_grid_charge_power_kw"),
                _reservation_value(
                    rolling_reservation, "requested_grid_charge_power_kw"
                ),
                _reservation_value(full_reservation, "allowed_grid_charge_power_kw"),
                _reservation_value(rolling_reservation, "allowed_grid_charge_power_kw"),
                _number(
                    _signed_power(
                        full_candidate.intent.action, full_candidate.requested_power_kw
                    )
                ),
                _number(
                    _signed_power(
                        rolling_candidate.intent.action,
                        rolling_candidate.requested_power_kw,
                    )
                ),
                _number(
                    _signed_power(
                        full_physical.intent.action, full_physical.requested_power_kw
                    )
                ),
                _number(
                    _signed_power(
                        rolling_physical.intent.action,
                        rolling_physical.requested_power_kw,
                    )
                ),
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


def _window_metadata(
    steps: tuple[PVOpportunityWindowStep, ...],
) -> tuple[str, str, str, str]:
    if not steps:
        return "", "", "", ""
    first = steps[0]
    last = steps[-1]
    start = first.forecast_point.timestamp.isoformat()
    end = last.forecast_point.timestamp.isoformat()
    indexes = "|".join(str(step.source_index) for step in steps)
    return start, end, indexes, str(len(steps))


def _reservation_value(reservation: object | None, field_name: str) -> str:
    if reservation is None:
        return ""
    value = getattr(reservation, field_name)
    if not isinstance(value, float):
        raise TypeError(f"reservation {field_name} must be a float")
    return _number(value)


def _signed_power(action: str, magnitude: float) -> float:
    if action == "charge":
        return magnitude
    if action == "discharge":
        return -magnitude
    if action == "idle":
        return 0.0
    raise ValueError("unexpected semantic action")


def _number(value: float) -> str:
    return f"{value:.6f}"


def _pv_absorption(
    result: HeadroomAwareExplainableMPCDailySimulationResult
    | RollingHeadroomAwareExplainableMPCDailySimulationResult,
) -> PVAbsorptionMetrics:
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


def _required_headroom_svg(
    full: HeadroomAwareExplainableMPCDailySimulationResult,
    rolling: RollingHeadroomAwareExplainableMPCDailySimulationResult,
) -> str:
    full_values = tuple(
        trace.headroom_mpc_cycle_result.headroom_optimization_output.headroom_requirement.required_headroom_energy_kwh
        for trace in full.step_traces
    )
    rolling_values = tuple(
        trace.rolling_headroom_mpc_cycle_result.rolling_headroom_optimization_output.rolling_headroom_requirement.headroom_requirement.required_headroom_energy_kwh
        for trace in rolling.step_traces
    )
    maximum = max(1.0, *full_values, *rolling_values)
    return _two_series_svg(
        "Required headroom comparison (kWh)",
        "Full horizon headroom",
        full_values,
        "Rolling opportunity headroom",
        rolling_values,
        0.0,
        maximum,
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
    full_values = tuple(
        trace.simulation_trace.state.grid_result.actual_grid_power_kw
        for trace in full.step_traces
    )
    rolling_values = tuple(
        trace.simulation_trace.state.grid_result.actual_grid_power_kw
        for trace in rolling.step_traces
    )
    maximum = max(1.0, *(abs(value) for value in (*full_values, *rolling_values)))
    return _two_series_svg(
        "Actual grid power comparison (positive = import)",
        "Full horizon grid",
        full_values,
        "Rolling opportunity grid",
        rolling_values,
        -maximum,
        maximum,
    )


def _summary_text(
    full_result: HeadroomAwareExplainableMPCDailySimulationResult,
    rolling_result: RollingHeadroomAwareExplainableMPCDailySimulationResult,
    full: HeadroomComparisonMetrics,
    rolling: HeadroomComparisonMetrics,
    full_pv: PVAbsorptionMetrics,
    rolling_pv: PVAbsorptionMetrics,
) -> str:
    rolling_windows = tuple(
        trace.rolling_headroom_mpc_cycle_result.rolling_headroom_optimization_output.rolling_headroom_requirement.opportunity_window
        for trace in rolling_result.step_traces
    )
    first = next((window for window in rolling_windows if window.steps), None)
    second = next(
        (
            window
            for window in rolling_windows
            if first is not None
            and window.steps
            and window.steps[0].forecast_point.timestamp
            > first.steps[-1].forecast_point.timestamp
            and window.start_index == 0
        ),
        None,
    )
    transition_cycle = next(
        (
            index
            for index, window in enumerate(rolling_windows)
            if first is not None
            and window.steps
            and window.steps[0].forecast_point.timestamp
            > first.steps[-1].forecast_point.timestamp
        ),
        None,
    )
    early_full = full_result.step_traces[
        0
    ].headroom_mpc_cycle_result.headroom_optimization_output
    early_rolling = rolling_result.step_traces[
        0
    ].rolling_headroom_mpc_cycle_result.rolling_headroom_optimization_output
    full_requested = _reservation_power(early_full, "requested_grid_charge_power_kw")
    full_allowed = _reservation_power(early_full, "allowed_grid_charge_power_kw")
    rolling_requested = _reservation_power(
        early_rolling, "requested_grid_charge_power_kw"
    )
    rolling_allowed = _reservation_power(early_rolling, "allowed_grid_charge_power_kw")
    transition_text = "" if transition_cycle is None else str(transition_cycle)
    import_delta = rolling.grid_import_energy_kwh - full.grid_import_energy_kwh
    export_delta = rolling.grid_export_energy_kwh - full.grid_export_energy_kwh
    soc_delta = rolling.final_soc - full.final_soc
    full_hour_14 = full_result.step_traces[14].simulation_trace.state
    rolling_hour_14 = rolling_result.step_traces[14].simulation_trace.state
    return (
        "EOS Multi-Opportunity Rolling Headroom Behavioral Validation\n"
        "scenario=finite 24-hour diagnostic day; low-price no-PV 00:00-05:00; "
        "PV opportunities 08:00-10:00 and 14:00-17:00; non-surplus gap 11:00-13:00\n"
        f"gap_tolerance_points={_GAP_TOLERANCE_POINTS}\n"
        "This scenario is intentionally diagnostic and is not claimed to represent "
        "a universal household profile.\n"
        "pre_pv_hour_00\n"
        f"full_required_headroom_kwh={early_full.headroom_requirement.required_headroom_energy_kwh:.6f}\n"
        "rolling_required_headroom_kwh="
        f"{early_rolling.rolling_headroom_requirement.headroom_requirement.required_headroom_energy_kwh:.6f}\n"
        f"full_recommended_max_soc={early_full.headroom_requirement.recommended_pre_pv_max_soc_fraction:.6f}\n"
        "rolling_recommended_max_soc="
        f"{early_rolling.rolling_headroom_requirement.headroom_requirement.recommended_pre_pv_max_soc_fraction:.6f}\n"
        f"full_requested_grid_charge_kw={full_requested}\n"
        f"full_allowed_grid_charge_kw={full_allowed}\n"
        f"rolling_requested_grid_charge_kw={rolling_requested}\n"
        f"rolling_allowed_grid_charge_kw={rolling_allowed}\n"
        "full_horizon\n"
        + _metrics_text(full, full_pv)
        + "rolling_opportunity\n"
        + _metrics_text(rolling, rolling_pv)
        + "rolling_opportunities\n"
        + f"first_start={_window_start(first)}\n"
        + f"first_end={_window_end(first)}\n"
        + f"second_start={_window_start(second)}\n"
        + f"second_end={_window_end(second)}\n"
        + f"selector_transition_cycle={transition_text}\n"
        + "deltas_rolling_minus_full\n"
        + f"grid_import_energy_kwh={import_delta:.6f}\n"
        + f"grid_export_energy_kwh={export_delta:.6f}\n"
        + f"final_soc={soc_delta:.6f}\n"
        + "interpretation\n"
        + "Accounting, reservation, and realized control are reported separately.\n"
        + "At 00:00 rolling admits additional cheap-grid charge because its target "
        + "is less conservative.\n"
        + "At 14:00 full/rolling actual battery charge is "
        + f"{full_hour_14.battery_result.actual_power_kw:.6f}/"
        + f"{rolling_hour_14.battery_result.actual_power_kw:.6f} kW; actual grid "
        + "power is "
        + f"{full_hour_14.grid_result.actual_grid_power_kw:.6f}/"
        + f"{rolling_hour_14.grid_result.actual_grid_power_kw:.6f} kW.\n"
    )


def _reservation_power(
    output: HeadroomAwarePhysicalOptimizationSolveOutput
    | RollingHeadroomAwarePhysicalOptimizationSolveOutput,
    field_name: str,
) -> str:
    reservation = output.candidate_planning_result.grid_charge_reservation
    if reservation is None:
        return ""
    return _number(getattr(reservation, field_name))


def _window_start(window: PVOpportunityWindow | None) -> str:
    if window is None:
        return ""
    return window.steps[0].forecast_point.timestamp.isoformat()


def _window_end(window: PVOpportunityWindow | None) -> str:
    if window is None:
        return ""
    return window.steps[-1].forecast_point.timestamp.isoformat()


def _metrics_text(
    metrics: HeadroomComparisonMetrics,
    pv: PVAbsorptionMetrics,
) -> str:
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
        f"total_pv_surplus_energy_kwh={pv.total_pv_surplus_energy_kwh:.6f}\n"
        "estimated_absorbed_pv_surplus_energy_kwh="
        f"{pv.estimated_absorbed_pv_surplus_energy_kwh:.6f}\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
