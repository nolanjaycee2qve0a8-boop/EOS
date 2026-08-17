# ruff: noqa: E501
"""Deterministic Residential EMS 1.0 reference demonstration.

This integration/demo composes established schedule-aware and economic
schedule-aware MPC paths.  It owns the explicit residential facts and
read-model outputs only; scheduling, economic gating, physical revision,
feasibility, handoff, simulation, ledger, and comparison semantics remain in
their respective TASK-090--174 boundaries.
"""

import argparse
import csv
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from io import StringIO
from math import isclose
from pathlib import Path

from ems_simulator.economic_comparison_explanation import (
    DeterministicEconomicComparisonExplainer,
    EconomicComparisonExplanation,
    EconomicComparisonInput,
    comparison_summary_csv,
    format_economic_comparison_explanation,
)
from ems_simulator.economic_ledger import (
    DailyEconomicLedger,
    DeterministicEconomicLedgerBuilder,
    EconomicLedgerInput,
)
from ems_simulator.economic_multi_opportunity_explainable_mpc_daily import (
    EconomicMultiOpportunityExplainableMPCDailySimulationResult,
    EconomicMultiOpportunityExplainableMPCDailySimulationStepTrace,
)
from ems_simulator.economic_schedule_aware_comparison_demo import (
    EconomicComparisonScenario,
    _economic_runner,
    _inputs,
    _schedule_runner,
)
from ems_simulator.multi_opportunity_explainable_mpc_daily import (
    MultiOpportunityExplainableMPCDailySimulationInput,
    MultiOpportunityExplainableMPCDailySimulationResult,
    MultiOpportunityExplainableMPCDailySimulationStepTrace,
)
from optimization import (
    BatteryOptimizationModel,
    EconomicGridChargeValueResult,
    MultiOpportunityGridChargeReservationResult,
    NetLoadAwareBaselineOptimizationConfiguration,
)

_EXPORT_TARIFF_PER_KWH = 0.20
_DEGRADATION_COST_PER_THROUGHPUT_KWH = 0.05
_TERMINAL_VALUATION_PRICE = 0.85
_HOURS_PER_DAY = 24

# This readable TOU profile intentionally offers low-price overnight grid
# charging, normal daytime operation, and high-price evening discharge.
_IMPORT_TARIFF_PER_KWH = (0.20,) * 6 + (0.50,) * 12 + (0.90,) * 4 + (0.50,) * 2


@dataclass(frozen=True, slots=True)
class ResidentialReferencePath:
    """One completed control path and its read-only daily accounting."""

    name: str
    result: (
        MultiOpportunityExplainableMPCDailySimulationResult
        | EconomicMultiOpportunityExplainableMPCDailySimulationResult
    )
    ledger: DailyEconomicLedger


@dataclass(frozen=True, slots=True)
class ResidentialReferenceResult:
    """Retain exact two-path artifacts and deterministic output locations."""

    schedule_input: MultiOpportunityExplainableMPCDailySimulationInput
    economic_input: MultiOpportunityExplainableMPCDailySimulationInput
    schedule: ResidentialReferencePath
    economic: ResidentialReferencePath
    comparison: EconomicComparisonExplanation
    timeseries_csv_path: Path
    summary_csv_path: Path
    comparison_csv_path: Path
    explanation_path: Path
    power_svg_path: Path
    soc_svg_path: Path
    tariff_svg_path: Path
    economic_components_svg_path: Path


ScheduleTrace = MultiOpportunityExplainableMPCDailySimulationStepTrace
EconomicTrace = EconomicMultiOpportunityExplainableMPCDailySimulationStepTrace
ReferenceTrace = ScheduleTrace | EconomicTrace


def run_residential_reference_demo(
    output_directory: Path,
) -> ResidentialReferenceResult:
    """Run one fair, finite, deterministic residential A/B reference day."""

    if not isinstance(output_directory, Path):
        raise TypeError("output_directory must be a pathlib.Path")
    output_directory.mkdir(parents=True, exist_ok=True)
    scenario = EconomicComparisonScenario(
        "RESIDENTIAL_REFERENCE",
        "Residential 24-hour perfect-forecast TOU reference.",
        _IMPORT_TARIFF_PER_KWH,
        NetLoadAwareBaselineOptimizationConfiguration(0.30, 0.80, 3.0),
    )
    schedule_input, economic_input = _inputs(scenario, output_directory)
    if (
        schedule_input.daily_mpc_input.integration_input
        is not economic_input.daily_mpc_input.integration_input
    ):
        raise AssertionError(
            "reference paths must share exact exogenous integration facts"
        )
    if (
        schedule_input.daily_mpc_input.forecast_horizons
        is not economic_input.daily_mpc_input.forecast_horizons
    ):
        raise AssertionError(
            "reference paths must share exact caller forecast horizons"
        )
    if (
        schedule_input.daily_mpc_input.battery_optimization_model
        is not economic_input.daily_mpc_input.battery_optimization_model
    ):
        raise AssertionError("reference paths must share exact battery model")

    configuration = scenario.candidate_configuration
    schedule_result = _schedule_runner(configuration).run(schedule_input)
    economic_result = _economic_runner(configuration).run(economic_input)
    model = schedule_input.daily_mpc_input.battery_optimization_model
    schedule = ResidentialReferencePath(
        "Schedule",
        schedule_result,
        _ledger(schedule_result, model),
    )
    economic = ResidentialReferencePath(
        "Economic",
        economic_result,
        _ledger(economic_result, model),
    )
    comparison = DeterministicEconomicComparisonExplainer().explain(
        EconomicComparisonInput(
            schedule.name,
            economic.name,
            schedule.ledger.extended_outcome_evidence,
            economic.ledger.extended_outcome_evidence,
            scenario.scenario_id,
            "Export tariff 0.20, degradation 0.05/kWh throughput, terminal valuation 0.85/kWh.",
        )
    )
    _validate_reference(
        schedule,
        economic,
        comparison,
        model.min_soc_fraction,
        model.max_soc_fraction,
        model.max_charge_power_kw,
        model.max_discharge_power_kw,
    )

    timeseries_csv_path = output_directory / "residential_reference_timeseries.csv"
    summary_csv_path = output_directory / "residential_reference_summary.csv"
    comparison_csv_path = (
        output_directory / "residential_reference_economic_comparison.csv"
    )
    explanation_path = output_directory / "residential_reference_explanation.txt"
    power_svg_path = output_directory / "residential_power_flow.svg"
    soc_svg_path = output_directory / "residential_soc.svg"
    tariff_svg_path = output_directory / "residential_tariff.svg"
    economic_components_svg_path = (
        output_directory / "residential_economic_components.svg"
    )
    timeseries_csv_path.write_text(
        _timeseries_csv(schedule, economic), encoding="utf-8", newline=""
    )
    summary_csv_path.write_text(
        _summary_csv((schedule, economic)), encoding="utf-8", newline=""
    )
    comparison_csv_path.write_text(
        comparison_summary_csv((comparison,)), encoding="utf-8", newline=""
    )
    explanation_path.write_text(
        _explanation_text(schedule, economic, comparison), encoding="utf-8", newline=""
    )
    power_svg_path.write_text(
        _power_svg(schedule, economic), encoding="utf-8", newline=""
    )
    soc_svg_path.write_text(
        _line_svg(
            "Actual battery SOC",
            (("Schedule", _socs(schedule)), ("Economic", _socs(economic))),
            "SOC fraction",
        ),
        encoding="utf-8",
        newline="",
    )
    tariff_svg_path.write_text(
        _line_svg(
            "Import tariff", (("Import tariff", _tariffs(schedule)),), "currency/kWh"
        ),
        encoding="utf-8",
        newline="",
    )
    economic_components_svg_path.write_text(
        _economic_components_svg(comparison), encoding="utf-8", newline=""
    )
    return ResidentialReferenceResult(
        schedule_input,
        economic_input,
        schedule,
        economic,
        comparison,
        timeseries_csv_path,
        summary_csv_path,
        comparison_csv_path,
        explanation_path,
        power_svg_path,
        soc_svg_path,
        tariff_svg_path,
        economic_components_svg_path,
    )


def _ledger(
    trajectory: MultiOpportunityExplainableMPCDailySimulationResult
    | EconomicMultiOpportunityExplainableMPCDailySimulationResult,
    model: BatteryOptimizationModel,
) -> DailyEconomicLedger:
    return DeterministicEconomicLedgerBuilder().build(
        EconomicLedgerInput(
            trajectory,
            (_EXPORT_TARIFF_PER_KWH,) * _HOURS_PER_DAY,
            (_DEGRADATION_COST_PER_THROUGHPUT_KWH,) * _HOURS_PER_DAY,
            _TERMINAL_VALUATION_PRICE,
            model,
        )
    )


def _validate_reference(
    schedule: ResidentialReferencePath,
    economic: ResidentialReferencePath,
    comparison: EconomicComparisonExplanation,
    minimum_soc: float,
    maximum_soc: float,
    max_charge_power: float,
    max_discharge_power: float,
) -> None:
    for path in (schedule, economic):
        if len(path.ledger.intervals) != _HOURS_PER_DAY:
            raise AssertionError("reference path must have exactly 24 ledger intervals")
        for trace, interval in zip(_traces(path), path.ledger.intervals, strict=True):
            state = trace.simulation_trace.state
            battery = state.battery_result.actual_power_kw
            grid = state.grid_result.actual_grid_power_kw
            load = state.load_result.actual_power_kw
            pv = state.pv_result.actual_power_kw
            if not minimum_soc <= interval.soc_after_fraction <= maximum_soc:
                raise AssertionError(
                    "actual simulator SOC must remain within battery bounds"
                )
            if battery > max_charge_power or -battery > max_discharge_power:
                raise AssertionError(
                    "actual simulator power must remain within battery limits"
                )
            if not isclose(pv + grid - battery, load, rel_tol=0.0, abs_tol=1e-12):
                raise AssertionError(
                    "simulator grid power must reconcile with hourly balance"
                )
        if not isclose(
            path.ledger.adjusted_net_economic_cost,
            path.ledger.extended_outcome_evidence.adjusted_net_economic_cost,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise AssertionError("daily ledger must reconcile to TASK-168 outcome")
    if not isclose(
        comparison.delta_adjusted_cost,
        sum(
            (
                comparison.import_cost_contribution,
                comparison.export_revenue_contribution,
                comparison.degradation_cost_contribution,
                comparison.terminal_value_contribution,
            )
        ),
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise AssertionError("TASK-174 comparison decomposition must reconcile")


def _timeseries_csv(
    schedule: ResidentialReferencePath, economic: ResidentialReferencePath
) -> str:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        (
            "timestamp",
            "pv_power_kw",
            "load_power_kw",
            "schedule_battery_power_kw",
            "schedule_grid_power_kw",
            "schedule_soc_fraction",
            "economic_battery_power_kw",
            "economic_grid_power_kw",
            "economic_soc_fraction",
            "import_tariff_per_kwh",
            "export_tariff_per_kwh",
            "economic_supported_grid_charge_kw",
            "headroom_limited",
            "physical_revision",
            "schedule_action",
            "economic_action",
        )
    )
    for schedule_trace, economic_trace in zip(
        _traces(schedule), _economic_traces(economic), strict=True
    ):
        state = schedule_trace.simulation_trace.state
        timestamp = state.battery_result.simulation_input.step_identity.timestamp
        if timestamp is None:
            raise AssertionError("reference simulation steps require timestamps")
        economic_value = _economic_value(economic_trace)
        reservation = _reservation(economic_trace)
        writer.writerow(
            (
                timestamp.isoformat(),
                *_numbers(
                    (
                        state.pv_result.actual_power_kw,
                        state.load_result.actual_power_kw,
                        state.battery_result.actual_power_kw,
                        state.grid_result.actual_grid_power_kw,
                        state.battery_result.next_state.soc,
                        economic_trace.simulation_trace.state.battery_result.actual_power_kw,
                        economic_trace.simulation_trace.state.grid_result.actual_grid_power_kw,
                        economic_trace.simulation_trace.state.battery_result.next_state.soc,
                        state.tariff_result.import_price_cny_per_kwh,
                        _EXPORT_TARIFF_PER_KWH,
                    )
                ),
                ""
                if economic_value is None
                else _number(
                    economic_value.economically_supported_grid_charge_power_kw
                ),
                ""
                if reservation is None
                else str(reservation.reservation_applied).lower(),
                str(economic_trace.journal_record.revision_applied).lower(),
                schedule_trace.journal_record.final_action.action,
                economic_trace.journal_record.final_action.action,
            )
        )
    return stream.getvalue()


def _summary_csv(paths: Iterable[ResidentialReferencePath]) -> str:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        (
            "path",
            "load_energy_kwh",
            "pv_energy_kwh",
            "grid_import_energy_kwh",
            "grid_export_energy_kwh",
            "battery_throughput_kwh",
            "final_soc_fraction",
            "realized_import_cost",
            "realized_export_revenue",
            "battery_degradation_cost",
            "realized_net_cost",
            "terminal_energy_value",
            "adjusted_net_economic_cost",
        )
    )
    for path in paths:
        ledger = path.ledger
        writer.writerow(
            (
                path.name,
                *_numbers(
                    (
                        ledger.total_load_energy_kwh,
                        ledger.total_pv_energy_kwh,
                        ledger.total_grid_import_energy_kwh,
                        ledger.total_grid_export_energy_kwh,
                        ledger.total_battery_throughput_kwh,
                        ledger.final_soc_fraction,
                        ledger.total_realized_import_cost,
                        ledger.total_realized_export_revenue,
                        ledger.total_battery_degradation_cost,
                        ledger.total_realized_net_cost,
                        ledger.terminal_energy_value,
                        ledger.adjusted_net_economic_cost,
                    )
                ),
            )
        )
    return stream.getvalue()


def _explanation_text(
    schedule: ResidentialReferencePath,
    economic: ResidentialReferencePath,
    comparison: EconomicComparisonExplanation,
) -> str:
    daily = schedule.result.source_input.daily_mpc_input.integration_input.daily_input
    model = schedule.result.source_input.daily_mpc_input.battery_optimization_model
    blocks = [
        "Residential Reference Scenario\n",
        "Deterministic 24 x 1-hour residential EMS 1.0 reference. Export is intentionally allowed and settled at the explicit demo tariff; zero-export is not active.\n\n",
        "System Configuration\n",
        f"Battery: usable capacity={_number(model.usable_capacity_kwh)} kWh; initial SOC={_number(daily.initial_soc)}; min/max SOC={_number(model.min_soc_fraction)}/{_number(model.max_soc_fraction)}; max charge/discharge={_number(model.max_charge_power_kw)}/{_number(model.max_discharge_power_kw)} kW; charge/discharge efficiency={_number(model.charge_efficiency)}/{_number(model.discharge_efficiency)}.\n\n",
        "Forecast Assumptions\n",
        "Perfect, deterministic caller-supplied 24-point horizons are intentional for a repeatable reference. This is not evidence of real-weather or forecast-error robustness.\n\n",
        "Control Behavior\n",
        "Facts -> Forecast -> Economic/Schedule planning -> ControlPlan -> CurrentAction -> EMSDecision -> Feasibility -> Actuation -> Simulator -> actual SOC feedback. Projected SOC is not reused as actual feedback.\n",
        "Grid charging is requested only during low-price/no-PV-surplus candidate periods when the existing schedule/headroom path allows it; PV surplus charge bypasses cheap-grid economic gating. Discharge is bounded upstream by net load and then physically revised if needed.\n\n",
        "Energy Results\n",
        _path_text(schedule),
        _path_text(economic),
        "\n",
        "Economic Results\n",
        _economic_text(schedule),
        _economic_text(economic),
        "\n",
        "Economic vs Schedule Comparison\n",
        format_economic_comparison_explanation(comparison),
        "\n",
        "Representative Decision Explanations\n",
        _representative_text(schedule, economic),
        "\n",
        "Known Limitations\n",
        "This reference demo does not prove real-weather robustness, forecast-error robustness, real PCS/BMS integration, communication reliability, actual battery-aging economics, real tariff applicability, industrial-site behavior, or multiple-storage-device behavior. Export tariff, degradation rate, and terminal valuation are demo accounting assumptions only; terminal valuation is not a control shadow price.\n",
    ]
    return "".join(blocks)


def _path_text(path: ResidentialReferencePath) -> str:
    ledger = path.ledger
    return f"{path.name}: load={_number(ledger.total_load_energy_kwh)} kWh; PV={_number(ledger.total_pv_energy_kwh)} kWh; grid import/export={_number(ledger.total_grid_import_energy_kwh)}/{_number(ledger.total_grid_export_energy_kwh)} kWh; throughput={_number(ledger.total_battery_throughput_kwh)} kWh; final SOC={_number(ledger.final_soc_fraction)}.\n"


def _economic_text(path: ResidentialReferencePath) -> str:
    ledger = path.ledger
    return f"{path.name}: import cost={_number(ledger.total_realized_import_cost)}; export revenue={_number(ledger.total_realized_export_revenue)}; degradation={_number(ledger.total_battery_degradation_cost)}; realized net={_number(ledger.total_realized_net_cost)}; terminal value={_number(ledger.terminal_energy_value)}; adjusted net={_number(ledger.adjusted_net_economic_cost)}.\n"


def _representative_text(
    schedule: ResidentialReferencePath, economic: ResidentialReferencePath
) -> str:
    daily = schedule.result.source_input.daily_mpc_input.integration_input.daily_input
    selected: list[tuple[str, int]] = [("Overnight cheap tariff", 0)]
    selected.append(
        (
            "Midday PV surplus",
            next(
                index
                for index, (pv, load) in enumerate(
                    zip(daily.pv_power_curve_kw, daily.load_power_curve_kw, strict=True)
                )
                if pv > load
            ),
        )
    )
    selected.append(
        (
            "Evening high-price deficit",
            next(
                index
                for index, price in enumerate(daily.tariff_curve_cny_per_kwh)
                if price >= 0.90
            ),
        )
    )
    selected.append(
        (
            "Idle/no-action",
            next(
                index
                for index, trace in enumerate(_economic_traces(economic))
                if trace.journal_record.final_action.action == "idle"
            ),
        )
    )
    return "".join(
        _representative_line(label, index, schedule, economic)
        for label, index in selected
    )


def _representative_line(
    label: str,
    index: int,
    schedule: ResidentialReferencePath,
    economic: ResidentialReferencePath,
) -> str:
    schedule_record = schedule.result.journal_records[index]
    economic_trace = _economic_traces(economic)[index]
    economic_record = economic_trace.journal_record
    value = _economic_value(economic_trace)
    reservation = _reservation(economic_trace)
    economic_reason = (
        "PV/discharge/idle bypass"
        if value is None
        else f"economic={value.economic_classification.value}, supported_grid_charge={_number(value.economically_supported_grid_charge_power_kw)} kW"
    )
    headroom = (
        "no reservation"
        if reservation is None
        else f"headroom_allowed={_number(reservation.allowed_grid_charge_power_kw)} kW"
    )
    return f"- {label} ({economic_record.timestamp.isoformat()}): Schedule final={schedule_record.final_action.action}/{_number(schedule_record.final_requested_power_kw)} kW; Economic candidate={economic_record.candidate_action.action}/{_number(economic_record.candidate_requested_power_kw)} kW -> final={economic_record.final_action.action}/{_number(economic_record.final_requested_power_kw)} kW; {economic_reason}; {headroom}; physical_revision={str(economic_record.revision_applied).lower()} reasons={'|'.join(economic_record.revision_reasons) or 'none'}.\n"


def _economic_value(
    trace: EconomicTrace,
) -> EconomicGridChargeValueResult | None:
    return trace.economic_multi_opportunity_mpc_cycle_result.economic_multi_opportunity_optimization_output.candidate_planning_result.economic_value_result


def _reservation(
    trace: EconomicTrace,
) -> MultiOpportunityGridChargeReservationResult | None:
    return trace.economic_multi_opportunity_mpc_cycle_result.economic_multi_opportunity_optimization_output.candidate_planning_result.reservation_result


def _socs(path: ResidentialReferencePath) -> tuple[float, ...]:
    return tuple(
        trace.simulation_trace.state.battery_result.next_state.soc
        for trace in _traces(path)
    )


def _tariffs(path: ResidentialReferencePath) -> tuple[float, ...]:
    return tuple(
        trace.simulation_trace.state.tariff_result.import_price_cny_per_kwh
        for trace in _traces(path)
    )


def _power_svg(
    schedule: ResidentialReferencePath, economic: ResidentialReferencePath
) -> str:
    return _line_svg(
        "Actual power flow",
        (
            (
                "PV",
                tuple(
                    trace.simulation_trace.state.pv_result.actual_power_kw
                    for trace in _traces(schedule)
                ),
            ),
            (
                "Load",
                tuple(
                    trace.simulation_trace.state.load_result.actual_power_kw
                    for trace in _traces(schedule)
                ),
            ),
            (
                "Schedule battery",
                tuple(
                    trace.simulation_trace.state.battery_result.actual_power_kw
                    for trace in _traces(schedule)
                ),
            ),
            (
                "Economic battery",
                tuple(
                    trace.simulation_trace.state.battery_result.actual_power_kw
                    for trace in _traces(economic)
                ),
            ),
        ),
        "kW",
    )


def _traces(path: ResidentialReferencePath) -> tuple[ReferenceTrace, ...]:
    if isinstance(path.result, MultiOpportunityExplainableMPCDailySimulationResult):
        return path.result.step_traces
    return path.result.step_traces


def _economic_traces(
    path: ResidentialReferencePath,
) -> tuple[EconomicTrace, ...]:
    if not isinstance(
        path.result,
        EconomicMultiOpportunityExplainableMPCDailySimulationResult,
    ):
        raise TypeError("economic reference path must retain economic daily traces")
    return path.result.step_traces


def _economic_components_svg(comparison: EconomicComparisonExplanation) -> str:
    values = (
        ("Import", comparison.import_cost_contribution),
        ("Export", comparison.export_revenue_contribution),
        ("Degradation", comparison.degradation_cost_contribution),
        ("Terminal", comparison.terminal_value_contribution),
    )
    maximum = max(1.0, *(abs(value) for _, value in values))
    bars = "".join(
        f'<rect x="{70 + index * 145}" y="{180 - max(value, 0.0) / maximum * 105:.1f}" width="68" height="{abs(value) / maximum * 105:.1f}" fill="{"#1f77b4" if value <= 0 else "#d95f02"}"/><text x="{70 + index * 145}" y="205" font-size="12">{label}</text><text x="{70 + index * 145}" y="222" font-size="11">{value:+.3f}</text>'
        for index, (label, value) in enumerate(values)
    )
    return _svg(
        "Economic - Schedule adjusted-cost contributions",
        f'<line x1="45" y1="180" x2="650" y2="180" stroke="#777"/>{bars}',
        "Negative helps Economic; positive helps Schedule.",
    )


def _line_svg(
    title: str, series: tuple[tuple[str, tuple[float, ...]], ...], unit: str
) -> str:
    all_values = tuple(value for _, values in series for value in values)
    lower = min(0.0, min(all_values))
    upper = max(1.0, max(all_values))
    span = upper - lower
    colors = ("#1f77b4", "#d95f02", "#2ca02c", "#9467bd")
    paths = []
    labels = []
    for index, (name, values) in enumerate(series):
        points = " ".join(
            f"{55 + step * 25:.1f},{180 - (value - lower) / span * 120:.1f}"
            for step, value in enumerate(values)
        )
        color = colors[index]
        paths.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{points}"/>'
        )
        labels.append(
            f'<text x="{55 + index * 145}" y="238" fill="{color}" font-size="12">{name}</text>'
        )
    return _svg(
        title,
        f'<line x1="55" y1="180" x2="640" y2="180" stroke="#777"/><text x="8" y="65" font-size="11">{upper:.2f} {unit}</text><text x="8" y="185" font-size="11">{lower:.2f}</text>{"".join(paths)}{"".join(labels)}',
        "Hours 00 through 23; actual Simulator values.",
    )


def _svg(title: str, content: str, footer: str) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="700" height="280" viewBox="0 0 700 280"><rect width="700" height="280" fill="white"/><text x="24" y="30" font-family="Arial, sans-serif" font-size="18" font-weight="bold">{title}</text>{content}<text x="24" y="266" font-family="Arial, sans-serif" font-size="11" fill="#555">{footer}</text></svg>'


def _numbers(values: Iterable[float]) -> tuple[str, ...]:
    return tuple(_number(value) for value in values)


def _number(value: float) -> str:
    return f"{value:.6f}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="EOS Residential EMS 1.0 reference demo"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("simulation_output_task175_residential_reference"),
    )
    arguments = parser.parse_args(argv)
    result = run_residential_reference_demo(arguments.output_dir)
    for path in (
        result.timeseries_csv_path,
        result.summary_csv_path,
        result.comparison_csv_path,
        result.explanation_path,
        result.power_svg_path,
        result.soc_svg_path,
        result.tariff_svg_path,
        result.economic_components_svg_path,
    ):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
