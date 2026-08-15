# ruff: noqa: E501
"""Observe terminal-SOC divergence through the frozen economic control paths.

TASK-165 reuses TASK-161's established Schedule-aware and Economic
Schedule-aware daily runners.  It only changes caller-owned scenario facts,
then reads completed actual traces and TASK-162/163 evidence; it owns no
optimization, reservation, MPC, feasibility, actuation, or Simulator logic.
"""

import argparse
import csv
from collections.abc import Sequence
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

from ems_simulator.economic_multi_opportunity_explainable_mpc_daily import (
    EconomicMultiOpportunityExplainableMPCDailySimulationResult,
    EconomicMultiOpportunityExplainableMPCDailySimulationStepTrace,
)
from ems_simulator.economic_schedule_aware_comparison_demo import (
    DailyMetrics,
    _daily_metrics,
    _economic_metrics,
    _economic_runner,
    _finite_horizons,
    _schedule_runner,
)
from ems_simulator.ems_integration import EMSIntegrationScenarioInput
from ems_simulator.explainable_mpc_daily import ExplainableMPCDailySimulationInput
from ems_simulator.input import DailySimulationScenarioInput
from ems_simulator.multi_opportunity_explainable_mpc_daily import (
    MultiOpportunityExplainableMPCDailySimulationInput,
    MultiOpportunityExplainableMPCDailySimulationResult,
    MultiOpportunityExplainableMPCDailySimulationStepTrace,
)
from ems_simulator.multi_opportunity_headroom_demo import (
    _GAP_TOLERANCE_POINTS,
    create_demo_input,
)
from optimization import (
    BatteryOptimizationModel,
    DeterministicEconomicOutcomeCalculator,
    DeterministicTerminalEnergyValueCalculator,
    EconomicGridChargeValueResult,
    EconomicOutcomeBoundary,
    EconomicOutcomeEvidence,
    EconomicOutcomeInput,
    NetLoadAwareBaselineOptimizationConfiguration,
    PVOpportunityWindowConfiguration,
    TerminalEnergyValueBoundary,
    TerminalEnergyValueEvidence,
    TerminalEnergyValueInput,
)

_HOURS_PER_DAY = 24
_INITIAL_SOC = 0.50
_PV_CAP_KW = 0.60
_TARIFF_PROFILE = (0.80,) * 6 + (0.85,) * 18
_CONFIGURATION = NetLoadAwareBaselineOptimizationConfiguration(0.80, 1.00, 3.0)


@dataclass(frozen=True, slots=True)
class TerminalSOCDivergenceScenario:
    """Caller-owned facts deliberately preserving an early economic gate effect."""

    description: str
    initial_soc: float
    pv_cap_kw: float
    tariff_profile_cny_per_kwh: tuple[float, ...]
    candidate_configuration: NetLoadAwareBaselineOptimizationConfiguration


@dataclass(frozen=True, slots=True)
class TerminalSOCDivergencePathResult:
    """One actual daily path and exact terminal/outcome evidence."""

    source_metrics: DailyMetrics
    terminal_energy_value_evidence: TerminalEnergyValueEvidence
    economic_outcome_evidence: EconomicOutcomeEvidence
    grid_charge_energy_kwh: float
    suppressed_grid_charge_energy_kwh: float

    def __post_init__(self) -> None:
        if not isinstance(self.source_metrics, DailyMetrics):
            raise TypeError("source_metrics must be a DailyMetrics")
        if not isinstance(
            self.terminal_energy_value_evidence,
            TerminalEnergyValueEvidence,
        ):
            raise TypeError(
                "terminal_energy_value_evidence must be a TerminalEnergyValueEvidence"
            )
        if not isinstance(self.economic_outcome_evidence, EconomicOutcomeEvidence):
            raise TypeError(
                "economic_outcome_evidence must be an EconomicOutcomeEvidence"
            )
        if (
            self.economic_outcome_evidence.terminal_energy_value_evidence
            is not self.terminal_energy_value_evidence
        ):
            raise ValueError("outcome must preserve exact terminal evidence identity")
        if (
            self.economic_outcome_evidence.realized_import_cost
            != self.source_metrics.grid_import_cost
        ):
            raise ValueError("outcome must preserve exact realized import cost")


@dataclass(frozen=True, slots=True)
class TerminalSOCDivergenceDeltas:
    """Economic minus Schedule evidence; no ranking assumption is encoded."""

    realized_import_cost: float
    grid_import_energy_kwh: float
    grid_export_energy_kwh: float
    absorbed_pv_surplus_kwh: float
    battery_throughput_kwh: float
    final_soc: float
    usable_terminal_stored_energy_kwh: float
    deliverable_terminal_energy_kwh: float
    terminal_energy_value: float
    net_economic_cost: float
    grid_charge_energy_kwh: float
    suppressed_grid_charge_energy_kwh: float


@dataclass(frozen=True, slots=True)
class TerminalSOCDivergenceResult:
    """Complete observable comparison, including exact completed runner results."""

    scenario: TerminalSOCDivergenceScenario
    schedule_input: MultiOpportunityExplainableMPCDailySimulationInput
    economic_input: MultiOpportunityExplainableMPCDailySimulationInput
    schedule_result: MultiOpportunityExplainableMPCDailySimulationResult
    economic_result: EconomicMultiOpportunityExplainableMPCDailySimulationResult
    schedule: TerminalSOCDivergencePathResult
    economic: TerminalSOCDivergencePathResult
    deltas_economic_minus_schedule: TerminalSOCDivergenceDeltas
    first_divergence_index: int
    first_divergence_timestamp: str
    comparison_csv_path: Path
    hourly_trajectory_csv_path: Path
    daily_summary_path: Path
    soc_divergence_svg_path: Path
    realized_vs_terminal_value_svg_path: Path
    net_economic_cost_svg_path: Path


def scenario_definition() -> TerminalSOCDivergenceScenario:
    """Return the fixed 24-hour diagnostic profile definition.

    The first six 0.80-price hours are cheap-grid candidate intervals. Their
    best later 0.85 price produces a negative gross margin at 0.95 x 0.95
    efficiency.  The original daytime PV shape is capped at 0.60 kW, below
    normal load, so later PV cannot make the actual SOC paths converge.
    """

    return TerminalSOCDivergenceScenario(
        "Finite 24h profile: early negative-margin grid charging, then weak PV below load and no later discharge trigger.",
        _INITIAL_SOC,
        _PV_CAP_KW,
        _TARIFF_PROFILE,
        _CONFIGURATION,
    )


def run_terminal_soc_divergence_evaluation(
    output_directory: Path,
    terminal_value_calculator: TerminalEnergyValueBoundary | None = None,
    outcome_calculator: EconomicOutcomeBoundary | None = None,
) -> TerminalSOCDivergenceResult:
    """Run each existing daily path once and only then attach accounting evidence."""

    if not isinstance(output_directory, Path):
        raise TypeError("output_directory must be a pathlib.Path")
    terminal_calculator = (
        DeterministicTerminalEnergyValueCalculator()
        if terminal_value_calculator is None
        else terminal_value_calculator
    )
    net_cost_calculator = (
        DeterministicEconomicOutcomeCalculator()
        if outcome_calculator is None
        else outcome_calculator
    )
    if not isinstance(terminal_calculator, TerminalEnergyValueBoundary):
        raise TypeError(
            "terminal_value_calculator must be a TerminalEnergyValueBoundary"
        )
    if not isinstance(net_cost_calculator, EconomicOutcomeBoundary):
        raise TypeError("outcome_calculator must be an EconomicOutcomeBoundary")

    scenario = scenario_definition()
    output_directory.mkdir(parents=True, exist_ok=True)
    schedule_input, economic_input = _inputs(scenario, output_directory)
    schedule_result = _schedule_runner(scenario.candidate_configuration).run(
        schedule_input
    )
    economic_result = _economic_runner(scenario.candidate_configuration).run(
        economic_input
    )
    schedule_metrics = _daily_metrics(schedule_result)
    economic_metrics = _daily_metrics(economic_result)
    economic_evidence_metrics = _economic_metrics(economic_result)
    battery_model = schedule_input.daily_mpc_input.battery_optimization_model
    if economic_input.daily_mpc_input.battery_optimization_model is not battery_model:
        raise ValueError("both paths must preserve exact battery model identity")
    valuation_import_price = max(scenario.tariff_profile_cny_per_kwh)
    schedule_path = _evaluate_path(
        schedule_metrics,
        schedule_result,
        battery_model,
        valuation_import_price,
        0.0,
        terminal_calculator,
        net_cost_calculator,
    )
    economic_path = _evaluate_path(
        economic_metrics,
        economic_result,
        battery_model,
        valuation_import_price,
        economic_evidence_metrics.economically_suppressed_grid_charge_energy_kwh,
        terminal_calculator,
        net_cost_calculator,
    )
    first_index = _first_divergence_index(schedule_result, economic_result)
    timestamp = (
        schedule_result.step_traces[first_index]
        .forecast_horizon.points[0]
        .timestamp.isoformat()
    )
    deltas = _deltas(schedule_path, economic_path)
    comparison_csv_path = output_directory / "terminal_soc_divergence_comparison.csv"
    hourly_trajectory_csv_path = output_directory / "hourly_trajectory.csv"
    daily_summary_path = output_directory / "evaluation_summary.txt"
    soc_divergence_svg_path = output_directory / "soc_divergence.svg"
    realized_vs_terminal_value_svg_path = (
        output_directory / "realized_vs_terminal_value.svg"
    )
    net_economic_cost_svg_path = output_directory / "net_economic_cost.svg"
    comparison_csv_path.write_text(
        _comparison_csv(schedule_path, economic_path, deltas),
        encoding="utf-8",
        newline="",
    )
    hourly_trajectory_csv_path.write_text(
        _hourly_trajectory_csv(schedule_result, economic_result),
        encoding="utf-8",
        newline="",
    )
    daily_summary_path.write_text(
        _daily_summary(
            scenario,
            schedule_path,
            economic_path,
            deltas,
            first_index,
            timestamp,
        ),
        encoding="utf-8",
        newline="",
    )
    soc_divergence_svg_path.write_text(
        _two_series_svg(
            "Actual SOC divergence: Schedule-aware vs Economic",
            _next_socs(schedule_result),
            _next_socs(economic_result),
        ),
        encoding="utf-8",
    )
    realized_vs_terminal_value_svg_path.write_text(
        _two_metric_svg(
            "Realized import cost and terminal energy value",
            schedule_path,
            economic_path,
        ),
        encoding="utf-8",
    )
    net_economic_cost_svg_path.write_text(
        _paired_bar_svg(
            "Terminal-value-adjusted net economic cost",
            schedule_path.economic_outcome_evidence.net_economic_cost,
            economic_path.economic_outcome_evidence.net_economic_cost,
        ),
        encoding="utf-8",
    )
    return TerminalSOCDivergenceResult(
        scenario,
        schedule_input,
        economic_input,
        schedule_result,
        economic_result,
        schedule_path,
        economic_path,
        deltas,
        first_index,
        timestamp,
        comparison_csv_path,
        hourly_trajectory_csv_path,
        daily_summary_path,
        soc_divergence_svg_path,
        realized_vs_terminal_value_svg_path,
        net_economic_cost_svg_path,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="EOS TASK-165 terminal SOC divergence economic observation"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("simulation_output_task165_terminal_soc_divergence"),
    )
    arguments = parser.parse_args(argv)
    result = run_terminal_soc_divergence_evaluation(arguments.output_dir)
    for path in (
        result.comparison_csv_path,
        result.hourly_trajectory_csv_path,
        result.daily_summary_path,
        result.soc_divergence_svg_path,
        result.realized_vs_terminal_value_svg_path,
        result.net_economic_cost_svg_path,
    ):
        print(path)
    return 0


def _inputs(
    scenario: TerminalSOCDivergenceScenario,
    output_directory: Path,
) -> tuple[
    MultiOpportunityExplainableMPCDailySimulationInput,
    MultiOpportunityExplainableMPCDailySimulationInput,
]:
    template = create_demo_input(output_directory)
    template_daily = template.integration_input.daily_input
    pv_profile = tuple(
        min(value, scenario.pv_cap_kw) for value in template_daily.pv_power_curve_kw
    )
    daily = DailySimulationScenarioInput(
        template_daily.step_identities,
        pv_profile,
        template_daily.load_power_curve_kw,
        scenario.tariff_profile_cny_per_kwh,
        template_daily.battery_parameters,
        scenario.initial_soc,
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
            schedule_daily,
            scenario.candidate_configuration,
            opportunity,
        ),
        MultiOpportunityExplainableMPCDailySimulationInput(
            economic_daily,
            scenario.candidate_configuration,
            opportunity,
        ),
    )


def _evaluate_path(
    metrics: DailyMetrics,
    result: MultiOpportunityExplainableMPCDailySimulationResult
    | EconomicMultiOpportunityExplainableMPCDailySimulationResult,
    battery_model: BatteryOptimizationModel,
    valuation_import_price: float,
    suppressed_grid_charge_energy_kwh: float,
    terminal_calculator: TerminalEnergyValueBoundary,
    outcome_calculator: EconomicOutcomeBoundary,
) -> TerminalSOCDivergencePathResult:
    terminal_evidence = terminal_calculator.calculate(
        TerminalEnergyValueInput(
            metrics.final_soc,
            battery_model,
            valuation_import_price,
        )
    )
    outcome_evidence = outcome_calculator.calculate(
        EconomicOutcomeInput(metrics.grid_import_cost, terminal_evidence)
    )
    return TerminalSOCDivergencePathResult(
        metrics,
        terminal_evidence,
        outcome_evidence,
        _grid_charge_energy(result),
        suppressed_grid_charge_energy_kwh,
    )


def _grid_charge_energy(
    result: MultiOpportunityExplainableMPCDailySimulationResult
    | EconomicMultiOpportunityExplainableMPCDailySimulationResult,
) -> float:
    """Read actual grid-charge energy from completed traces; do not change control."""

    total = 0.0
    for trace in result.step_traces:
        state = trace.simulation_trace.state
        duration = (
            trace.simulation_trace.simulation_input.step_identity.duration_seconds
            / 3600.0
        )
        if state.pv_result.actual_power_kw <= state.load_result.actual_power_kw:
            total += max(state.battery_result.actual_power_kw, 0.0) * duration
    return total


def _deltas(
    schedule: TerminalSOCDivergencePathResult,
    economic: TerminalSOCDivergencePathResult,
) -> TerminalSOCDivergenceDeltas:
    schedule_metrics = schedule.source_metrics
    economic_metrics = economic.source_metrics
    schedule_terminal = schedule.terminal_energy_value_evidence
    economic_terminal = economic.terminal_energy_value_evidence
    return TerminalSOCDivergenceDeltas(
        economic.economic_outcome_evidence.realized_import_cost
        - schedule.economic_outcome_evidence.realized_import_cost,
        economic_metrics.grid_import_energy_kwh
        - schedule_metrics.grid_import_energy_kwh,
        economic_metrics.grid_export_energy_kwh
        - schedule_metrics.grid_export_energy_kwh,
        economic_metrics.absorbed_pv_surplus_kwh
        - schedule_metrics.absorbed_pv_surplus_kwh,
        economic_metrics.battery_throughput_kwh
        - schedule_metrics.battery_throughput_kwh,
        economic_metrics.final_soc - schedule_metrics.final_soc,
        economic_terminal.usable_terminal_stored_energy_kwh
        - schedule_terminal.usable_terminal_stored_energy_kwh,
        economic_terminal.deliverable_terminal_energy_kwh
        - schedule_terminal.deliverable_terminal_energy_kwh,
        economic_terminal.terminal_energy_value
        - schedule_terminal.terminal_energy_value,
        economic.economic_outcome_evidence.net_economic_cost
        - schedule.economic_outcome_evidence.net_economic_cost,
        economic.grid_charge_energy_kwh - schedule.grid_charge_energy_kwh,
        economic.suppressed_grid_charge_energy_kwh
        - schedule.suppressed_grid_charge_energy_kwh,
    )


def _first_divergence_index(
    schedule: MultiOpportunityExplainableMPCDailySimulationResult,
    economic: EconomicMultiOpportunityExplainableMPCDailySimulationResult,
) -> int:
    for index, (schedule_trace, economic_trace) in enumerate(
        zip(schedule.step_traces, economic.step_traces, strict=True)
    ):
        if (
            schedule_trace.simulation_trace.state.battery_result.next_state.soc
            != economic_trace.simulation_trace.state.battery_result.next_state.soc
        ):
            return index
    raise ValueError(
        "diagnostic scenario did not produce actual terminal SOC divergence"
    )


def _comparison_csv(
    schedule: TerminalSOCDivergencePathResult,
    economic: TerminalSOCDivergencePathResult,
    deltas: TerminalSOCDivergenceDeltas,
) -> str:
    rows = (
        (
            "realized_import_cost",
            schedule.economic_outcome_evidence.realized_import_cost,
            economic.economic_outcome_evidence.realized_import_cost,
            deltas.realized_import_cost,
        ),
        (
            "grid_import_kwh",
            schedule.source_metrics.grid_import_energy_kwh,
            economic.source_metrics.grid_import_energy_kwh,
            deltas.grid_import_energy_kwh,
        ),
        (
            "grid_export_kwh",
            schedule.source_metrics.grid_export_energy_kwh,
            economic.source_metrics.grid_export_energy_kwh,
            deltas.grid_export_energy_kwh,
        ),
        (
            "absorbed_pv_surplus_kwh",
            schedule.source_metrics.absorbed_pv_surplus_kwh,
            economic.source_metrics.absorbed_pv_surplus_kwh,
            deltas.absorbed_pv_surplus_kwh,
        ),
        (
            "battery_throughput_kwh",
            schedule.source_metrics.battery_throughput_kwh,
            economic.source_metrics.battery_throughput_kwh,
            deltas.battery_throughput_kwh,
        ),
        (
            "final_soc",
            schedule.source_metrics.final_soc,
            economic.source_metrics.final_soc,
            deltas.final_soc,
        ),
        (
            "usable_terminal_stored_energy_kwh",
            schedule.terminal_energy_value_evidence.usable_terminal_stored_energy_kwh,
            economic.terminal_energy_value_evidence.usable_terminal_stored_energy_kwh,
            deltas.usable_terminal_stored_energy_kwh,
        ),
        (
            "deliverable_terminal_energy_kwh",
            schedule.terminal_energy_value_evidence.deliverable_terminal_energy_kwh,
            economic.terminal_energy_value_evidence.deliverable_terminal_energy_kwh,
            deltas.deliverable_terminal_energy_kwh,
        ),
        (
            "terminal_energy_value",
            schedule.terminal_energy_value_evidence.terminal_energy_value,
            economic.terminal_energy_value_evidence.terminal_energy_value,
            deltas.terminal_energy_value,
        ),
        (
            "net_economic_cost",
            schedule.economic_outcome_evidence.net_economic_cost,
            economic.economic_outcome_evidence.net_economic_cost,
            deltas.net_economic_cost,
        ),
        (
            "grid_charge_energy_kwh",
            schedule.grid_charge_energy_kwh,
            economic.grid_charge_energy_kwh,
            deltas.grid_charge_energy_kwh,
        ),
        (
            "suppressed_grid_charge_kwh",
            schedule.suppressed_grid_charge_energy_kwh,
            economic.suppressed_grid_charge_energy_kwh,
            deltas.suppressed_grid_charge_energy_kwh,
        ),
    )
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        ("metric", "schedule_value", "economic_value", "economic_minus_schedule")
    )
    writer.writerows(
        (name, _number(left), _number(right), _number(delta))
        for name, left, right, delta in rows
    )
    return stream.getvalue()


def _hourly_trajectory_csv(
    schedule: MultiOpportunityExplainableMPCDailySimulationResult,
    economic: EconomicMultiOpportunityExplainableMPCDailySimulationResult,
) -> str:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        (
            "timestamp",
            "schedule_soc",
            "economic_soc",
            "schedule_battery_power_kw",
            "economic_battery_power_kw",
            "schedule_grid_power_kw",
            "economic_grid_power_kw",
            "schedule_import_price",
            "economic_classification",
            "economic_gross_margin",
            "schedule_candidate_charge_kw",
            "economic_supported_charge_kw",
        )
    )
    for schedule_trace, economic_trace in zip(
        schedule.step_traces,
        economic.step_traces,
        strict=True,
    ):
        schedule_state = schedule_trace.simulation_trace.state
        economic_state = economic_trace.simulation_trace.state
        economic_value = _economic_value(economic_trace)
        schedule_candidate = _schedule_candidate_charge(schedule_trace)
        writer.writerow(
            (
                economic_trace.forecast_horizon.points[0].timestamp.isoformat(),
                _number(schedule_state.battery_result.next_state.soc),
                _number(economic_state.battery_result.next_state.soc),
                _number(schedule_state.battery_result.actual_power_kw),
                _number(economic_state.battery_result.actual_power_kw),
                _number(schedule_state.grid_result.actual_grid_power_kw),
                _number(economic_state.grid_result.actual_grid_power_kw),
                _number(schedule_state.tariff_result.import_price_cny_per_kwh),
                ""
                if economic_value is None
                else economic_value.economic_classification.value,
                ""
                if economic_value is None
                else _optional_number(
                    economic_value.economic_step_evidence.gross_shift_margin_per_grid_input_kwh
                ),
                _number(schedule_candidate),
                ""
                if economic_value is None
                else _number(
                    economic_value.economically_supported_grid_charge_power_kw
                ),
            )
        )
    return stream.getvalue()


def _economic_value(
    trace: EconomicMultiOpportunityExplainableMPCDailySimulationStepTrace,
) -> EconomicGridChargeValueResult | None:
    return trace.economic_multi_opportunity_mpc_cycle_result.economic_multi_opportunity_optimization_output.candidate_planning_result.economic_value_result


def _schedule_candidate_charge(
    trace: MultiOpportunityExplainableMPCDailySimulationStepTrace,
) -> float:
    step = trace.multi_opportunity_mpc_cycle_result.multi_opportunity_optimization_output.candidate_planning_result.final_output.solution.steps[
        0
    ]
    return step.requested_power_kw if step.intent.action == "charge" else 0.0


def _daily_summary(
    scenario: TerminalSOCDivergenceScenario,
    schedule: TerminalSOCDivergencePathResult,
    economic: TerminalSOCDivergencePathResult,
    deltas: TerminalSOCDivergenceDeltas,
    first_index: int,
    timestamp: str,
) -> str:
    return (
        "EOS Terminal-SOC-Divergence Economic Observation\n"
        f"scenario={scenario.description}\n"
        f"initial_soc={_number(scenario.initial_soc)} pv_cap_kw={_number(scenario.pv_cap_kw)} tariff_profile={','.join(_number(value) for value in scenario.tariff_profile_cny_per_kwh)}\n"
        "economic_gating=early 0.80 import price with best future 0.85 price is negative after 0.95 x 0.95 round-trip efficiency; Economic suppresses cheap-grid charge.\n"
        f"first_actual_soc_divergence=cycle {first_index} at {timestamp}\n"
        f"schedule: realized_import_cost={_number(schedule.economic_outcome_evidence.realized_import_cost)} final_soc={_number(schedule.source_metrics.final_soc)} terminal_value={_number(schedule.terminal_energy_value_evidence.terminal_energy_value)} net_economic_cost={_number(schedule.economic_outcome_evidence.net_economic_cost)} grid_charge_energy={_number(schedule.grid_charge_energy_kwh)}\n"
        f"economic: realized_import_cost={_number(economic.economic_outcome_evidence.realized_import_cost)} final_soc={_number(economic.source_metrics.final_soc)} terminal_value={_number(economic.terminal_energy_value_evidence.terminal_energy_value)} net_economic_cost={_number(economic.economic_outcome_evidence.net_economic_cost)} grid_charge_energy={_number(economic.grid_charge_energy_kwh)} suppressed_grid_charge_energy={_number(economic.suppressed_grid_charge_energy_kwh)}\n"
        f"economic_minus_schedule: realized_import_cost={_number(deltas.realized_import_cost)} terminal_soc={_number(deltas.final_soc)} deliverable_terminal_energy={_number(deltas.deliverable_terminal_energy_kwh)} terminal_value={_number(deltas.terminal_energy_value)} net_economic_cost={_number(deltas.net_economic_cost)}\n"
        f"conclusion: terminal value {'shrinks' if abs(deltas.net_economic_cost) < abs(deltas.realized_import_cost) else 'does not shrink'} the realized import-cost conclusion; ranking reversal is {'not observed' if deltas.net_economic_cost < 0.0 else 'observed'}.\n"
        "This remains limited accounting: import cost minus assigned terminal energy value, not full profit.\n"
    )


def _next_socs(
    result: MultiOpportunityExplainableMPCDailySimulationResult
    | EconomicMultiOpportunityExplainableMPCDailySimulationResult,
) -> tuple[float, ...]:
    return tuple(
        trace.simulation_trace.state.battery_result.next_state.soc
        for trace in result.step_traces
    )


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

    return _svg(
        title,
        f'<polyline fill="none" stroke="#2563eb" stroke-width="2" points="{points(schedule)}"/><polyline fill="none" stroke="#059669" stroke-width="2" points="{points(economic)}"/>',
        '<text x="70" y="325" fill="#2563eb">Schedule</text><text x="160" y="325" fill="#059669">Economic</text>',
    )


def _two_metric_svg(
    title: str,
    schedule: TerminalSOCDivergencePathResult,
    economic: TerminalSOCDivergencePathResult,
) -> str:
    values = (
        schedule.economic_outcome_evidence.realized_import_cost,
        schedule.terminal_energy_value_evidence.terminal_energy_value,
        economic.economic_outcome_evidence.realized_import_cost,
        economic.terminal_energy_value_evidence.terminal_energy_value,
    )
    maximum = max(1.0, *values)
    bars = "".join(
        f'<rect x="{90 + index * 50}" y="{255 - value / maximum * 210:.2f}" width="32" height="{value / maximum * 210:.2f}" fill="{("#2563eb", "#7dd3fc", "#059669", "#86efac")[index]}"/>'
        for index, value in enumerate(values)
    )
    footer = '<text x="90" y="285">Schedule cost</text><text x="210" y="285">Schedule terminal</text><text x="360" y="285">Economic cost</text><text x="480" y="285">Economic terminal</text>'
    return _svg(title, bars, footer)


def _paired_bar_svg(title: str, schedule: float, economic: float) -> str:
    maximum, minimum = max(1.0, schedule, economic), min(0.0, schedule, economic)
    scale = max(maximum - minimum, 1.0)
    baseline = 255.0 - (0.0 - minimum) / scale * 210.0
    bars = "".join(
        f'<rect x="{90 + index * 48}" y="{min(255.0 - (value - minimum) / scale * 210.0, baseline):.2f}" width="32" height="{abs(baseline - (255.0 - (value - minimum) / scale * 210.0)):.2f}" fill="{("#2563eb", "#059669")[index]}"/>'
        for index, value in enumerate((schedule, economic))
    )
    return _svg(
        title,
        bars,
        '<text x="90" y="285" fill="#2563eb">Schedule</text><text x="170" y="285" fill="#059669">Economic</text>',
    )


def _svg(title: str, content: str, footer: str) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="360" viewBox="0 0 1024 360"><rect width="100%" height="100%" fill="white"/><text x="70" y="28" font-family="sans-serif" font-size="16">{title}</text><line x1="70" y1="255" x2="980" y2="255" stroke="#64748b"/>{content}{footer}</svg>\n'


def _number(value: float) -> str:
    return f"{value:.6f}"


def _optional_number(value: float | None) -> str:
    return "" if value is None else _number(value)


if __name__ == "__main__":
    raise SystemExit(main())
