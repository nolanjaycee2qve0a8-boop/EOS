# ruff: noqa: E501
"""Measure TASK-152 and TASK-160 behaviour using identical caller facts.

This module is intentionally a read-model/demo composition.  It drives the
two established daily runners and reads their retained outer provenance plus
actual simulator traces.  It owns no economic, scheduling, candidate,
physical-revision, MPC, feasibility, or simulator algorithm.
"""

import argparse
import csv
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path

from ems_simulator.economic_multi_opportunity_explainable_mpc_daily import (
    EconomicMultiOpportunityExplainableMPCDailySimulationResult,
    EconomicMultiOpportunityExplainableMPCDailySimulationRunner,
)
from ems_simulator.ems_integration import EMSIntegrationScenarioInput
from ems_simulator.explainable_mpc_daily import ExplainableMPCDailySimulationInput
from ems_simulator.input import DailySimulationScenarioInput
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
from ems_strategy import (
    DeterministicExplainableMPCDecisionCSVFileExporter,
    DeterministicExplainableMPCDecisionCSVRowMapper,
    DeterministicExplainableMPCDecisionCSVSerializer,
    DeterministicExplainableMPCDecisionJournalRecordBuilder,
    DeterministicMPCDecisionExplanationBuilder,
    DeterministicMPCDecisionExplanationFormatter,
    EconomicMultiOpportunitySingleMPCCycleOrchestrator,
    FirstStepMPCCurrentActionExtractor,
    MultiOpportunitySingleMPCCycleOrchestrator,
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
    DeterministicMultiOpportunityCandidatePlanner,
    DeterministicMultiOpportunityGridChargeReservationCalculator,
    DeterministicMultiOpportunityHeadroomScheduleCalculator,
    DeterministicMultiOpportunityPhysicalOptimizer,
    DeterministicPVHeadroomRequirementCalculator,
    DeterministicPVOpportunitySequenceCalculator,
    EconomicShiftClassification,
    NetLoadAwareBaselineOptimizationConfiguration,
    NetLoadAwareBaselineOptimizer,
    OptimizationSolutionControlPlanBuilder,
    PVOpportunityWindowConfiguration,
)

_HOURS_PER_DAY = 24
_HORIZON_POINTS = 24
_ROUND_TRIP_EFFICIENCY = 0.95 * 0.95
_E2_FUTURE_PRICE = 0.80 / _ROUND_TRIP_EFFICIENCY


@dataclass(frozen=True, slots=True)
class EconomicComparisonScenario:
    """One caller-owned tariff/configuration scenario for the A/B observation."""

    scenario_id: str
    description: str
    tariff_profile_cny_per_kwh: tuple[float, ...]
    candidate_configuration: NetLoadAwareBaselineOptimizationConfiguration


@dataclass(frozen=True, slots=True)
class DailyMetrics:
    """Observed metrics derived solely from completed simulator traces."""

    pv_energy_kwh: float
    load_energy_kwh: float
    grid_import_energy_kwh: float
    grid_export_energy_kwh: float
    grid_import_cost: float
    battery_throughput_kwh: float
    final_soc: float
    absorbed_pv_surplus_kwh: float
    charge_count: int
    discharge_count: int
    idle_count: int
    physical_revision_count: int
    soc_limited_count: int
    power_limited_count: int


@dataclass(frozen=True, slots=True)
class EconomicDailyMetrics:
    """Read-only TASK-155/156 economic evidence totals for a completed day."""

    positive_cycles: int
    negative_cycles: int
    break_even_cycles: int
    unavailable_cycles: int
    economic_support_applied_count: int
    headroom_allowed_grid_charge_energy_kwh: float
    economically_supported_grid_charge_energy_kwh: float
    economically_suppressed_grid_charge_energy_kwh: float


@dataclass(frozen=True, slots=True)
class EconomicComparisonScenarioResult:
    """Retain the two exact completed paths and their observational metrics."""

    scenario: EconomicComparisonScenario
    schedule_input: MultiOpportunityExplainableMPCDailySimulationInput
    economic_input: MultiOpportunityExplainableMPCDailySimulationInput
    schedule_result: MultiOpportunityExplainableMPCDailySimulationResult
    economic_result: EconomicMultiOpportunityExplainableMPCDailySimulationResult
    schedule_metrics: DailyMetrics
    economic_metrics: DailyMetrics
    economic_evidence_metrics: EconomicDailyMetrics


@dataclass(frozen=True, slots=True)
class EconomicScheduleAwareComparisonResult:
    """All deterministic Task-161 measurements and output paths."""

    scenario_results: tuple[EconomicComparisonScenarioResult, ...]
    comparison_csv_path: Path
    scenario_summary_path: Path
    daily_summary_path: Path
    grid_import_cost_svg_path: Path
    suppressed_charge_svg_path: Path
    soc_e1_svg_path: Path
    grid_e1_svg_path: Path


def scenario_matrix() -> tuple[EconomicComparisonScenario, ...]:
    """Return E0/E1/E2 in stable caller order.

    All scenarios use the same TASK-154 S4 physical profile.  That fixture
    contains two separated PV opportunities but leaves some early schedule
    headroom, so the comparison can observe an actual cheap-grid gate.
    """

    profitable = (0.20,) * 6 + (0.50,) * 12 + (0.90,) * 4 + (0.50,) * 2
    negative = (0.80,) * 6 + (0.85,) * 18
    break_even = (0.80,) * 6 + (_E2_FUTURE_PRICE,) * 18
    return (
        EconomicComparisonScenario(
            "E0",
            "Clearly profitable 0.20 to 0.90 gross import-price shift.",
            profitable,
            NetLoadAwareBaselineOptimizationConfiguration(0.30, 0.80, 3.0),
        ),
        EconomicComparisonScenario(
            "E1",
            "Higher future price but negative after 0.95 x 0.95 efficiency.",
            negative,
            NetLoadAwareBaselineOptimizationConfiguration(0.80, 1.00, 3.0),
        ),
        EconomicComparisonScenario(
            "E2",
            "Future price equals current price divided by round-trip efficiency.",
            break_even,
            NetLoadAwareBaselineOptimizationConfiguration(0.80, 1.00, 3.0),
        ),
    )


def run_comparison(output_directory: Path) -> EconomicScheduleAwareComparisonResult:
    """Run the established A/B runners once for each caller-owned scenario."""

    if not isinstance(output_directory, Path):
        raise TypeError("output_directory must be a pathlib.Path")
    output_directory.mkdir(parents=True, exist_ok=True)
    results = tuple(
        _run_scenario(scenario, output_directory / scenario.scenario_id)
        for scenario in scenario_matrix()
    )
    comparison_csv_path = output_directory / "economic_schedule_aware_comparison.csv"
    scenario_summary_path = output_directory / "scenario_summary.csv"
    daily_summary_path = output_directory / "daily_summary.txt"
    grid_import_cost_svg_path = output_directory / "grid_import_cost_by_scenario.svg"
    suppressed_charge_svg_path = (
        output_directory / "suppressed_grid_charge_by_scenario.svg"
    )
    soc_e1_svg_path = output_directory / "soc_comparison_e1.svg"
    grid_e1_svg_path = output_directory / "grid_power_comparison_e1.svg"
    comparison_csv_path.write_text(
        _comparison_csv(results), encoding="utf-8", newline=""
    )
    scenario_summary_path.write_text(
        _summary_csv(results), encoding="utf-8", newline=""
    )
    daily_summary_path.write_text(_daily_summary(results), encoding="utf-8", newline="")
    grid_import_cost_svg_path.write_text(
        _paired_bar_svg("Actual grid import cost", results, _cost_values),
        encoding="utf-8",
    )
    suppressed_charge_svg_path.write_text(
        _single_bar_svg(
            "Economically suppressed cheap-grid charge (kWh)",
            results,
            lambda result: (
                result.economic_evidence_metrics.economically_suppressed_grid_charge_energy_kwh
            ),
        ),
        encoding="utf-8",
    )
    e1 = next(result for result in results if result.scenario.scenario_id == "E1")
    soc_e1_svg_path.write_text(
        _two_series_svg(
            "E1 actual SOC: Schedule-aware vs Economic",
            _next_socs(e1.schedule_result),
            _next_socs(e1.economic_result),
        ),
        encoding="utf-8",
    )
    grid_e1_svg_path.write_text(
        _two_series_svg(
            "E1 actual grid power (kW): Schedule-aware vs Economic",
            _grid_powers(e1.schedule_result),
            _grid_powers(e1.economic_result),
        ),
        encoding="utf-8",
    )
    return EconomicScheduleAwareComparisonResult(
        results,
        comparison_csv_path,
        scenario_summary_path,
        daily_summary_path,
        grid_import_cost_svg_path,
        suppressed_charge_svg_path,
        soc_e1_svg_path,
        grid_e1_svg_path,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="EOS schedule-aware versus economic schedule-aware comparison"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("simulation_output_task161_economic_comparison"),
    )
    arguments = parser.parse_args(argv)
    result = run_comparison(arguments.output_dir)
    for path in (
        result.comparison_csv_path,
        result.scenario_summary_path,
        result.daily_summary_path,
        result.grid_import_cost_svg_path,
        result.suppressed_charge_svg_path,
        result.soc_e1_svg_path,
        result.grid_e1_svg_path,
    ):
        print(path)
    return 0


def _run_scenario(
    scenario: EconomicComparisonScenario,
    output_directory: Path,
) -> EconomicComparisonScenarioResult:
    output_directory.mkdir(parents=True, exist_ok=True)
    schedule_input, economic_input = _inputs(scenario, output_directory)
    schedule_result = _schedule_runner(scenario.candidate_configuration).run(
        schedule_input
    )
    economic_result = _economic_runner(scenario.candidate_configuration).run(
        economic_input
    )
    return EconomicComparisonScenarioResult(
        scenario,
        schedule_input,
        economic_input,
        schedule_result,
        economic_result,
        _daily_metrics(schedule_result),
        _daily_metrics(economic_result),
        _economic_metrics(economic_result),
    )


def _inputs(
    scenario: EconomicComparisonScenario,
    output_directory: Path,
) -> tuple[
    MultiOpportunityExplainableMPCDailySimulationInput,
    MultiOpportunityExplainableMPCDailySimulationInput,
]:
    """Compose identical caller facts for both paths, with distinct output paths."""

    template = create_demo_input(output_directory)
    template_daily = template.integration_input.daily_input
    # TASK-154 S4: reduce the second surplus opportunity without changing its
    # separation from the first opportunity or the real non-surplus gap.
    pv = _replace_values(
        template_daily.pv_power_curve_kw,
        (14, 15, 16, 17),
        (1.8, 2.0, 1.8, 1.5),
    )
    daily = DailySimulationScenarioInput(
        template_daily.step_identities,
        pv,
        template_daily.load_power_curve_kw,
        scenario.tariff_profile_cny_per_kwh,
        template_daily.battery_parameters,
        0.50,
    )
    integration_template = template.integration_input
    integration = EMSIntegrationScenarioInput(
        daily,
        integration_template.objective_composition,
        integration_template.capability,
        integration_template.battery_power_limit_kw,
        integration_template.export_limit_kw,
        integration_template.initial_grid_power_kw,
    )
    horizons = _finite_horizons(daily)
    schedule_daily = ExplainableMPCDailySimulationInput(
        integration,
        horizons,
        template.mpc_configuration,
        template.optimization_objectives,
        template.source_strategy,
        template.battery_optimization_model,
        template.explanation_locale,
        output_directory / "schedule_mpc_decisions.csv",
    )
    economic_daily = ExplainableMPCDailySimulationInput(
        integration,
        horizons,
        template.mpc_configuration,
        template.optimization_objectives,
        template.source_strategy,
        template.battery_optimization_model,
        template.explanation_locale,
        output_directory / "economic_mpc_decisions.csv",
    )
    opportunity = PVOpportunityWindowConfiguration(_GAP_TOLERANCE_POINTS)
    return (
        MultiOpportunityExplainableMPCDailySimulationInput(
            schedule_daily, scenario.candidate_configuration, opportunity
        ),
        MultiOpportunityExplainableMPCDailySimulationInput(
            economic_daily, scenario.candidate_configuration, opportunity
        ),
    )


def _finite_horizons(
    daily: DailySimulationScenarioInput,
) -> tuple[ForecastHorizon, ...]:
    horizons: list[ForecastHorizon] = []
    for hour, identity in enumerate(daily.step_identities):
        timestamp = identity.timestamp
        if timestamp is None:
            raise ValueError("scenario steps require explicit timestamps")
        horizons.append(
            ForecastHorizon(
                tuple(
                    _forecast_point(
                        daily, hour + offset, timestamp + timedelta(hours=offset)
                    )
                    for offset in range(_HORIZON_POINTS)
                )
            )
        )
    return tuple(horizons)


def _forecast_point(
    daily: DailySimulationScenarioInput,
    index: int,
    timestamp: datetime,
) -> ForecastPoint:
    if index < _HOURS_PER_DAY:
        return ForecastPoint(
            timestamp,
            daily.pv_power_curve_kw[index],
            daily.load_power_curve_kw[index],
            daily.tariff_curve_cny_per_kwh[index],
        )
    return ForecastPoint(timestamp, 0.0, 0.0, 0.50)


def _schedule_runner(
    configuration: NetLoadAwareBaselineOptimizationConfiguration,
) -> MultiOpportunityExplainableMPCDailySimulationRunner:
    optimizer = DeterministicMultiOpportunityPhysicalOptimizer(
        DeterministicMultiOpportunityHeadroomScheduleCalculator(
            DeterministicPVOpportunitySequenceCalculator(),
            DeterministicPVHeadroomRequirementCalculator(),
        ),
        DeterministicMultiOpportunityCandidatePlanner(
            NetLoadAwareBaselineOptimizer(configuration),
            DeterministicMultiOpportunityGridChargeReservationCalculator(),
        ),
        _physical_reviser(),
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


def _economic_runner(
    configuration: NetLoadAwareBaselineOptimizationConfiguration,
) -> EconomicMultiOpportunityExplainableMPCDailySimulationRunner:
    optimizer = DeterministicEconomicMultiOpportunityPhysicalOptimizer(
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
        _physical_reviser(),
    )
    cycle = EconomicMultiOpportunitySingleMPCCycleOrchestrator(
        optimizer,
        OptimizationSolutionControlPlanBuilder(),
        FirstStepMPCCurrentActionExtractor(),
        _DemoMPCDecisionTranslator(),
    )
    return EconomicMultiOpportunityExplainableMPCDailySimulationRunner(
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


def _physical_reviser() -> DeterministicExplicitCandidatePhysicalReviser:
    return DeterministicExplicitCandidatePhysicalReviser(
        DeterministicBatterySOCHorizonProjector(),
        DeterministicBatterySOCHorizonConstraintEvaluator(),
        DeterministicBatteryPowerHorizonConstraintEvaluator(),
        DeterministicBatteryHorizonConstraintAggregator(),
    )


def _daily_metrics(
    result: MultiOpportunityExplainableMPCDailySimulationResult
    | EconomicMultiOpportunityExplainableMPCDailySimulationResult,
) -> DailyMetrics:
    pv_energy = load_energy = import_energy = export_energy = cost = throughput = 0.0
    absorbed = 0.0
    for trace in result.step_traces:
        state = trace.simulation_trace.state
        duration = (
            trace.simulation_trace.simulation_input.step_identity.duration_seconds
            / 3600.0
        )
        pv = state.pv_result.actual_power_kw
        load = state.load_result.actual_power_kw
        battery = state.battery_result.actual_power_kw
        grid = state.grid_result.actual_grid_power_kw
        price = state.tariff_result.import_price_cny_per_kwh
        pv_energy += pv * duration
        load_energy += load * duration
        import_energy += max(grid, 0.0) * duration
        export_energy += max(-grid, 0.0) * duration
        cost += max(grid, 0.0) * duration * price
        throughput += abs(battery) * duration
        absorbed += min(max(battery, 0.0), max(pv - load, 0.0)) * duration
    records = result.journal_records
    return DailyMetrics(
        pv_energy,
        load_energy,
        import_energy,
        export_energy,
        cost,
        throughput,
        result.step_traces[-1].simulation_trace.state.battery_result.next_state.soc,
        absorbed,
        sum(record.final_action.action == "charge" for record in records),
        sum(record.final_action.action == "discharge" for record in records),
        sum(record.final_action.action == "idle" for record in records),
        sum(record.revision_applied for record in records),
        sum(
            any(str(reason).endswith("soc_limit") for reason in record.revision_reasons)
            for record in records
        ),
        sum(
            any(
                str(reason).endswith("power_limit")
                for reason in record.revision_reasons
            )
            for record in records
        ),
    )


def _economic_metrics(
    result: EconomicMultiOpportunityExplainableMPCDailySimulationResult,
) -> EconomicDailyMetrics:
    classifications = {
        classification: 0 for classification in EconomicShiftClassification
    }
    applied = 0
    allowed = supported = suppressed = 0.0
    for trace in result.step_traces:
        planning = trace.economic_multi_opportunity_mpc_cycle_result.economic_multi_opportunity_optimization_output.candidate_planning_result
        value = planning.economic_value_result
        if value is None:
            continue
        classifications[value.economic_classification] += 1
        duration = (
            trace.simulation_trace.simulation_input.step_identity.duration_seconds
            / 3600.0
        )
        allowed += value.headroom_allowed_grid_charge_power_kw * duration
        supported += value.economically_supported_grid_charge_power_kw * duration
        suppressed += (
            max(
                value.headroom_allowed_grid_charge_power_kw
                - value.economically_supported_grid_charge_power_kw,
                0.0,
            )
            * duration
        )
        applied += value.economic_support_applied
    return EconomicDailyMetrics(
        classifications[EconomicShiftClassification.POSITIVE],
        classifications[EconomicShiftClassification.NEGATIVE],
        classifications[EconomicShiftClassification.BREAK_EVEN],
        classifications[EconomicShiftClassification.UNAVAILABLE],
        applied,
        allowed,
        supported,
        suppressed,
    )


def _comparison_csv(results: tuple[EconomicComparisonScenarioResult, ...]) -> str:
    columns = (
        "scenario_id",
        "timestamp",
        "pv_kw",
        "load_kw",
        "import_price",
        "schedule_soc",
        "economic_soc",
        "economic_classification",
        "economic_best_future_price",
        "economic_best_future_source_index",
        "economic_round_trip_efficiency",
        "economic_break_even_future_price",
        "economic_gross_margin",
        "schedule_requested_grid_charge_kw",
        "economic_requested_grid_charge_kw",
        "schedule_headroom_allowed_kw",
        "economic_headroom_allowed_kw",
        "economic_supported_grid_charge_kw",
        "economic_support_applied",
        "schedule_final_candidate_power_kw",
        "economic_final_candidate_power_kw",
        "schedule_actual_battery_power_kw",
        "economic_actual_battery_power_kw",
        "schedule_actual_grid_power_kw",
        "economic_actual_grid_power_kw",
        "schedule_next_soc",
        "economic_next_soc",
    )
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(columns)
    for result in results:
        for schedule_trace, economic_trace in zip(
            result.schedule_result.step_traces,
            result.economic_result.step_traces,
            strict=True,
        ):
            schedule_output = schedule_trace.multi_opportunity_mpc_cycle_result.multi_opportunity_optimization_output.candidate_planning_result
            economic_output = economic_trace.economic_multi_opportunity_mpc_cycle_result.economic_multi_opportunity_optimization_output.candidate_planning_result
            reservation = schedule_output.reservation_result
            value = economic_output.economic_value_result
            state = schedule_trace.simulation_trace.state
            economic_state = economic_trace.simulation_trace.state
            step = economic_trace.forecast_horizon.points[0]
            writer.writerow(
                (
                    result.scenario.scenario_id,
                    step.timestamp.isoformat(),
                    _number(state.pv_result.actual_power_kw),
                    _number(state.load_result.actual_power_kw),
                    _number(state.tariff_result.import_price_cny_per_kwh),
                    _number(
                        schedule_trace.simulation_trace.simulation_input.battery_input.source_state.soc
                    ),
                    _number(
                        economic_trace.simulation_trace.simulation_input.battery_input.source_state.soc
                    ),
                    "" if value is None else value.economic_classification.value,
                    ""
                    if value is None
                    else _optional_number(
                        value.economic_step_evidence.best_future_import_price_cny_per_kwh
                    ),
                    ""
                    if value is None
                    or value.economic_step_evidence.best_future_source_index is None
                    else str(value.economic_step_evidence.best_future_source_index),
                    ""
                    if value is None
                    else _number(value.economic_step_evidence.round_trip_efficiency),
                    ""
                    if value is None
                    else _optional_number(
                        value.economic_step_evidence.break_even_future_import_price_cny_per_kwh
                    ),
                    ""
                    if value is None
                    else _optional_number(
                        value.economic_step_evidence.gross_shift_margin_per_grid_input_kwh
                    ),
                    ""
                    if reservation is None
                    else _number(reservation.requested_grid_charge_power_kw),
                    ""
                    if value is None
                    else _number(value.requested_grid_charge_power_kw),
                    ""
                    if reservation is None
                    else _number(reservation.allowed_grid_charge_power_kw),
                    ""
                    if value is None
                    else _number(value.headroom_allowed_grid_charge_power_kw),
                    ""
                    if value is None
                    else _number(value.economically_supported_grid_charge_power_kw),
                    ""
                    if value is None
                    else str(value.economic_support_applied).lower(),
                    _number(
                        schedule_output.final_output.solution.steps[
                            0
                        ].requested_power_kw
                    ),
                    _number(
                        economic_output.final_output.solution.steps[
                            0
                        ].requested_power_kw
                    ),
                    _number(state.battery_result.actual_power_kw),
                    _number(economic_state.battery_result.actual_power_kw),
                    _number(state.grid_result.actual_grid_power_kw),
                    _number(economic_state.grid_result.actual_grid_power_kw),
                    _number(state.battery_result.next_state.soc),
                    _number(economic_state.battery_result.next_state.soc),
                )
            )
    return stream.getvalue()


def _summary_csv(results: tuple[EconomicComparisonScenarioResult, ...]) -> str:
    columns = (
        "scenario_id",
        "description",
        "schedule_grid_import_kwh",
        "economic_grid_import_kwh",
        "schedule_grid_export_kwh",
        "economic_grid_export_kwh",
        "schedule_grid_import_cost",
        "economic_grid_import_cost",
        "import_cost_delta_economic_minus_schedule",
        "schedule_battery_throughput_kwh",
        "economic_battery_throughput_kwh",
        "schedule_absorbed_pv_surplus_kwh",
        "economic_absorbed_pv_surplus_kwh",
        "schedule_final_soc",
        "economic_final_soc",
        "positive_cycles",
        "negative_cycles",
        "break_even_cycles",
        "unavailable_cycles",
        "headroom_allowed_grid_charge_energy_kwh",
        "economically_supported_grid_charge_energy_kwh",
        "economically_suppressed_grid_charge_energy_kwh",
    )
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(columns)
    for result in results:
        schedule = result.schedule_metrics
        economic = result.economic_metrics
        evidence = result.economic_evidence_metrics
        writer.writerow(
            (
                result.scenario.scenario_id,
                result.scenario.description,
                *(
                    _number(value)
                    for value in (
                        schedule.grid_import_energy_kwh,
                        economic.grid_import_energy_kwh,
                        schedule.grid_export_energy_kwh,
                        economic.grid_export_energy_kwh,
                        schedule.grid_import_cost,
                        economic.grid_import_cost,
                        economic.grid_import_cost - schedule.grid_import_cost,
                        schedule.battery_throughput_kwh,
                        economic.battery_throughput_kwh,
                        schedule.absorbed_pv_surplus_kwh,
                        economic.absorbed_pv_surplus_kwh,
                        schedule.final_soc,
                        economic.final_soc,
                    )
                ),
                evidence.positive_cycles,
                evidence.negative_cycles,
                evidence.break_even_cycles,
                evidence.unavailable_cycles,
                _number(evidence.headroom_allowed_grid_charge_energy_kwh),
                _number(evidence.economically_supported_grid_charge_energy_kwh),
                _number(evidence.economically_suppressed_grid_charge_energy_kwh),
            )
        )
    return stream.getvalue()


def _daily_summary(results: tuple[EconomicComparisonScenarioResult, ...]) -> str:
    blocks = [
        "EOS Economic Schedule-Aware Behavioral Comparison\n",
        "This is a deterministic measurement of existing TASK-152 and TASK-160 runners.\n",
        "Import-cost comparison excludes battery degradation, export revenue, auxiliary consumption, fixed charges, and uncertainty.\n\n",
    ]
    for result in results:
        evidence = result.economic_evidence_metrics
        representative = _representative_value(result.economic_result)
        blocks.append(
            f"[{result.scenario.scenario_id}] {result.scenario.description}\n"
            f"tariff_profile={','.join(_number(value) for value in result.scenario.tariff_profile_cny_per_kwh)}\n"
            f"representative_classification={representative[0]} margin={representative[1]}\n"
            f"schedule: {_metrics_line(result.schedule_metrics)}\n"
            f"economic: {_metrics_line(result.economic_metrics)}\n"
            f"observed_import_cost_delta_economic_minus_schedule={_number(result.economic_metrics.grid_import_cost - result.schedule_metrics.grid_import_cost)}\n"
            f"economic_evidence: positive={evidence.positive_cycles} negative={evidence.negative_cycles} break_even={evidence.break_even_cycles} unavailable={evidence.unavailable_cycles} headroom_allowed={_number(evidence.headroom_allowed_grid_charge_energy_kwh)} supported={_number(evidence.economically_supported_grid_charge_energy_kwh)} suppressed={_number(evidence.economically_suppressed_grid_charge_energy_kwh)}\n"
            "interpretation: economic evidence, candidate gating, actual control, and observed import cost are distinct layers. PV-surplus charging bypasses economic cheap-grid gating.\n\n"
        )
    return "".join(blocks)


def _representative_value(
    result: EconomicMultiOpportunityExplainableMPCDailySimulationResult,
) -> tuple[str, str]:
    for trace in result.step_traces:
        value = trace.economic_multi_opportunity_mpc_cycle_result.economic_multi_opportunity_optimization_output.candidate_planning_result.economic_value_result
        if value is not None:
            return (
                value.economic_classification.value,
                _optional_number(
                    value.economic_step_evidence.gross_shift_margin_per_grid_input_kwh
                ),
            )
    return ("", "")


def _metrics_line(metrics: DailyMetrics) -> str:
    return (
        f"import_kwh={_number(metrics.grid_import_energy_kwh)} export_kwh={_number(metrics.grid_export_energy_kwh)} "
        f"import_cost={_number(metrics.grid_import_cost)} throughput={_number(metrics.battery_throughput_kwh)} "
        f"final_soc={_number(metrics.final_soc)} absorbed_pv={_number(metrics.absorbed_pv_surplus_kwh)} "
        f"counts={metrics.charge_count}/{metrics.discharge_count}/{metrics.idle_count} revisions={metrics.physical_revision_count}"
    )


def _next_socs(
    result: MultiOpportunityExplainableMPCDailySimulationResult
    | EconomicMultiOpportunityExplainableMPCDailySimulationResult,
) -> tuple[float, ...]:
    return tuple(
        trace.simulation_trace.state.battery_result.next_state.soc
        for trace in result.step_traces
    )


def _grid_powers(
    result: MultiOpportunityExplainableMPCDailySimulationResult
    | EconomicMultiOpportunityExplainableMPCDailySimulationResult,
) -> tuple[float, ...]:
    return tuple(
        trace.simulation_trace.state.grid_result.actual_grid_power_kw
        for trace in result.step_traces
    )


def _cost_values(result: EconomicComparisonScenarioResult) -> tuple[float, float]:
    return (
        result.schedule_metrics.grid_import_cost,
        result.economic_metrics.grid_import_cost,
    )


def _paired_bar_svg(
    title: str,
    results: tuple[EconomicComparisonScenarioResult, ...],
    value_getter: Callable[[EconomicComparisonScenarioResult], tuple[float, float]],
) -> str:
    pairs = tuple(value_getter(result) for result in results)
    maximum = max(1.0, *(value for pair in pairs for value in pair))
    bars: list[str] = []
    for index, pair in enumerate(pairs):
        for offset, value in enumerate(pair):
            height = value / maximum * 210.0
            bars.append(
                f'<rect x="{90 + index * 180 + offset * 36}" y="{255 - height:.2f}" width="28" height="{height:.2f}" fill="{("#2563eb", "#059669")[offset]}"/>'
            )
    labels = "".join(
        f'<text x="{90 + index * 180}" y="280" font-size="12">{result.scenario.scenario_id}</text>'
        for index, result in enumerate(results)
    )
    return _svg(
        title,
        "".join(bars),
        labels
        + '<text x="90" y="325" fill="#2563eb">Schedule</text><text x="180" y="325" fill="#059669">Economic</text>',
    )


def _single_bar_svg(
    title: str,
    results: tuple[EconomicComparisonScenarioResult, ...],
    value_getter: Callable[[EconomicComparisonScenarioResult], float],
) -> str:
    values = tuple(value_getter(result) for result in results)
    maximum = max(1.0, *values)
    bars = "".join(
        f'<rect x="{90 + index * 180}" y="{255 - value / maximum * 210:.2f}" width="40" height="{value / maximum * 210:.2f}" fill="#dc2626"/>'
        for index, value in enumerate(values)
    )
    labels = "".join(
        f'<text x="{90 + index * 180}" y="280" font-size="12">{result.scenario.scenario_id}</text>'
        for index, result in enumerate(results)
    )
    return _svg(title, bars, labels)


def _two_series_svg(
    title: str, schedule: tuple[float, ...], economic: tuple[float, ...]
) -> str:
    maximum, minimum = max(1.0, *schedule, *economic), min(0.0, *schedule, *economic)
    scale = max(maximum - minimum, 1.0)

    def points(values: tuple[float, ...]) -> str:
        return " ".join(
            f"{70 + index * 34:.2f},{255 - (value - minimum) / scale * 210:.2f}"
            for index, value in enumerate(values)
        )

    content = f'<polyline fill="none" stroke="#2563eb" stroke-width="2" points="{points(schedule)}"/><polyline fill="none" stroke="#059669" stroke-width="2" points="{points(economic)}"/>'
    return _svg(
        title,
        content,
        '<text x="70" y="325" fill="#2563eb">Schedule</text><text x="160" y="325" fill="#059669">Economic</text>',
    )


def _svg(title: str, content: str, footer: str) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="360" viewBox="0 0 1024 360"><rect width="100%" height="100%" fill="white"/><text x="70" y="28" font-family="sans-serif" font-size="16">{title}</text><line x1="70" y1="255" x2="980" y2="255" stroke="#64748b"/>{content}{footer}</svg>\n'


def _replace_values(
    values: tuple[float, ...], indexes: tuple[int, ...], replacements: tuple[float, ...]
) -> tuple[float, ...]:
    changed = list(values)
    for index, replacement in zip(indexes, replacements, strict=True):
        changed[index] = replacement
    return tuple(changed)


def _number(value: float) -> str:
    return f"{value:.6f}"


def _optional_number(value: float | None) -> str:
    return "" if value is None else _number(value)


if __name__ == "__main__":
    raise SystemExit(main())
