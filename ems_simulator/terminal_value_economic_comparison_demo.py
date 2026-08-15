# ruff: noqa: E501
"""Re-evaluate frozen TASK-161 behavior with TASK-162/163 accounting evidence.

This observational module runs the exact existing TASK-161 comparison once, then
credits actual terminal stored-energy value against its already-observed import
cost. It owns no control, planning, MPC, feasibility, actuation, or simulator
logic and never recomputes either source evidence formula.
"""

import argparse
import csv
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

from ems_simulator.economic_schedule_aware_comparison_demo import (
    DailyMetrics,
    EconomicComparisonScenarioResult,
    EconomicScheduleAwareComparisonResult,
    run_comparison,
)
from optimization import (
    BatteryOptimizationModel,
    DeterministicEconomicOutcomeCalculator,
    DeterministicTerminalEnergyValueCalculator,
    EconomicOutcomeBoundary,
    EconomicOutcomeEvidence,
    EconomicOutcomeInput,
    TerminalEnergyValueBoundary,
    TerminalEnergyValueEvidence,
    TerminalEnergyValueInput,
)


@dataclass(frozen=True, slots=True)
class TerminalValueEconomicPathResult:
    """One exact TASK-161 path plus terminal-value-adjusted accounting evidence."""

    source_metrics: DailyMetrics
    terminal_energy_value_evidence: TerminalEnergyValueEvidence
    economic_outcome_evidence: EconomicOutcomeEvidence

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
            raise ValueError("economic outcome must retain exact terminal evidence")
        if (
            self.economic_outcome_evidence.realized_import_cost
            != self.source_metrics.grid_import_cost
        ):
            raise ValueError("economic outcome must retain exact TASK-161 import cost")


@dataclass(frozen=True, slots=True)
class TerminalValueEconomicDeltas:
    """Economic minus Schedule deltas; negative net cost favors Economic."""

    realized_import_cost: float
    terminal_energy_value: float
    net_economic_cost: float
    grid_import_energy_kwh: float
    grid_export_energy_kwh: float
    absorbed_pv_surplus_kwh: float
    battery_throughput_kwh: float
    final_soc: float


@dataclass(frozen=True, slots=True)
class TerminalValueEconomicScenarioResult:
    """Exact TASK-161 scenario result with two terminal-value accounting paths."""

    source_task_161_result: EconomicComparisonScenarioResult
    valuation_import_price: float
    schedule: TerminalValueEconomicPathResult
    economic: TerminalValueEconomicPathResult
    deltas_economic_minus_schedule: TerminalValueEconomicDeltas

    def __post_init__(self) -> None:
        if not isinstance(
            self.source_task_161_result, EconomicComparisonScenarioResult
        ):
            raise TypeError(
                "source_task_161_result must be an EconomicComparisonScenarioResult"
            )
        if self.valuation_import_price < 0.0:
            raise ValueError("valuation_import_price must be non-negative")
        if (
            self.schedule.source_metrics
            is not self.source_task_161_result.schedule_metrics
        ):
            raise ValueError("schedule metrics must retain exact TASK-161 identity")
        if (
            self.economic.source_metrics
            is not self.source_task_161_result.economic_metrics
        ):
            raise ValueError("economic metrics must retain exact TASK-161 identity")
        schedule_input = self.schedule.terminal_energy_value_evidence.source_input
        economic_input = self.economic.terminal_energy_value_evidence.source_input
        if schedule_input.valuation_import_price != self.valuation_import_price:
            raise ValueError(
                "schedule valuation price must preserve scenario semantics"
            )
        if economic_input.valuation_import_price != self.valuation_import_price:
            raise ValueError(
                "economic valuation price must preserve scenario semantics"
            )
        if schedule_input.battery_model is not economic_input.battery_model:
            raise ValueError("both paths must preserve exact battery model identity")


@dataclass(frozen=True, slots=True)
class TerminalValueEconomicComparisonResult:
    """All deterministic TASK-164 evaluation evidence and emitted artifacts."""

    source_task_161_result: EconomicScheduleAwareComparisonResult
    scenario_results: tuple[TerminalValueEconomicScenarioResult, ...]
    summary_csv_path: Path
    daily_summary_path: Path
    realized_import_cost_svg_path: Path
    terminal_energy_value_svg_path: Path
    net_economic_cost_svg_path: Path


def run_terminal_value_evaluation(
    output_directory: Path,
    terminal_value_calculator: TerminalEnergyValueBoundary | None = None,
    outcome_calculator: EconomicOutcomeBoundary | None = None,
) -> TerminalValueEconomicComparisonResult:
    """Run frozen TASK-161 once and add exactly one valuation/outcome per path.

    The common valuation price for both paths of one scenario is the maximum
    import price already present in that exact TASK-161 scenario tariff profile.
    The comparison layer deliberately does not choose a price per path.
    """

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

    output_directory.mkdir(parents=True, exist_ok=True)
    task_161 = run_comparison(output_directory / "task_161_baseline")
    results = tuple(
        _evaluate_scenario(item, terminal_calculator, net_cost_calculator)
        for item in task_161.scenario_results
    )
    summary_csv_path = output_directory / "terminal_value_economic_summary.csv"
    daily_summary_path = output_directory / "evaluation_summary.txt"
    realized_import_cost_svg_path = (
        output_directory / "realized_import_cost_by_scenario.svg"
    )
    terminal_energy_value_svg_path = (
        output_directory / "terminal_energy_value_by_scenario.svg"
    )
    net_economic_cost_svg_path = output_directory / "net_economic_cost_by_scenario.svg"
    summary_csv_path.write_text(_summary_csv(results), encoding="utf-8", newline="")
    daily_summary_path.write_text(_daily_summary(results), encoding="utf-8", newline="")
    realized_import_cost_svg_path.write_text(
        _paired_bar_svg(
            "Realized import cost by scenario",
            results,
            lambda item: (
                item.schedule.economic_outcome_evidence.realized_import_cost,
                item.economic.economic_outcome_evidence.realized_import_cost,
            ),
        ),
        encoding="utf-8",
    )
    terminal_energy_value_svg_path.write_text(
        _paired_bar_svg(
            "Terminal energy value by scenario",
            results,
            lambda item: (
                item.schedule.terminal_energy_value_evidence.terminal_energy_value,
                item.economic.terminal_energy_value_evidence.terminal_energy_value,
            ),
        ),
        encoding="utf-8",
    )
    net_economic_cost_svg_path.write_text(
        _paired_bar_svg(
            "Terminal-value-adjusted net economic cost by scenario",
            results,
            lambda item: (
                item.schedule.economic_outcome_evidence.net_economic_cost,
                item.economic.economic_outcome_evidence.net_economic_cost,
            ),
        ),
        encoding="utf-8",
    )
    return TerminalValueEconomicComparisonResult(
        task_161,
        results,
        summary_csv_path,
        daily_summary_path,
        realized_import_cost_svg_path,
        terminal_energy_value_svg_path,
        net_economic_cost_svg_path,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="EOS TASK-164 terminal-value-adjusted economic re-evaluation"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("simulation_output_task164_terminal_value"),
    )
    arguments = parser.parse_args(argv)
    result = run_terminal_value_evaluation(arguments.output_dir)
    for path in (
        result.summary_csv_path,
        result.daily_summary_path,
        result.realized_import_cost_svg_path,
        result.terminal_energy_value_svg_path,
        result.net_economic_cost_svg_path,
    ):
        print(path)
    return 0


def _evaluate_scenario(
    source: EconomicComparisonScenarioResult,
    terminal_calculator: TerminalEnergyValueBoundary,
    outcome_calculator: EconomicOutcomeBoundary,
) -> TerminalValueEconomicScenarioResult:
    schedule_model = source.schedule_input.daily_mpc_input.battery_optimization_model
    economic_model = source.economic_input.daily_mpc_input.battery_optimization_model
    if schedule_model is not economic_model:
        raise ValueError("TASK-161 paths must preserve exact shared battery model")
    valuation_import_price = max(source.scenario.tariff_profile_cny_per_kwh)
    schedule = _evaluate_path(
        source.schedule_metrics,
        schedule_model,
        valuation_import_price,
        terminal_calculator,
        outcome_calculator,
    )
    economic = _evaluate_path(
        source.economic_metrics,
        schedule_model,
        valuation_import_price,
        terminal_calculator,
        outcome_calculator,
    )
    return TerminalValueEconomicScenarioResult(
        source,
        valuation_import_price,
        schedule,
        economic,
        TerminalValueEconomicDeltas(
            economic.economic_outcome_evidence.realized_import_cost
            - schedule.economic_outcome_evidence.realized_import_cost,
            economic.terminal_energy_value_evidence.terminal_energy_value
            - schedule.terminal_energy_value_evidence.terminal_energy_value,
            economic.economic_outcome_evidence.net_economic_cost
            - schedule.economic_outcome_evidence.net_economic_cost,
            economic.source_metrics.grid_import_energy_kwh
            - schedule.source_metrics.grid_import_energy_kwh,
            economic.source_metrics.grid_export_energy_kwh
            - schedule.source_metrics.grid_export_energy_kwh,
            economic.source_metrics.absorbed_pv_surplus_kwh
            - schedule.source_metrics.absorbed_pv_surplus_kwh,
            economic.source_metrics.battery_throughput_kwh
            - schedule.source_metrics.battery_throughput_kwh,
            economic.source_metrics.final_soc - schedule.source_metrics.final_soc,
        ),
    )


def _evaluate_path(
    metrics: DailyMetrics,
    battery_model: BatteryOptimizationModel,
    valuation_import_price: float,
    terminal_calculator: TerminalEnergyValueBoundary,
    outcome_calculator: EconomicOutcomeBoundary,
) -> TerminalValueEconomicPathResult:
    # The type is validated by TASK-162; this composition deliberately retains
    # the exact established model object rather than reconstructing it.
    terminal_input = TerminalEnergyValueInput(
        metrics.final_soc,
        battery_model,
        valuation_import_price,
    )
    terminal_evidence = terminal_calculator.calculate(terminal_input)
    outcome_evidence = outcome_calculator.calculate(
        EconomicOutcomeInput(metrics.grid_import_cost, terminal_evidence)
    )
    return TerminalValueEconomicPathResult(
        metrics,
        terminal_evidence,
        outcome_evidence,
    )


def _summary_csv(results: tuple[TerminalValueEconomicScenarioResult, ...]) -> str:
    columns = (
        "scenario_id",
        "valuation_import_price",
        "schedule_realized_import_cost",
        "economic_realized_import_cost",
        "delta_realized_import_cost",
        "schedule_terminal_soc",
        "economic_terminal_soc",
        "delta_terminal_soc",
        "schedule_usable_terminal_stored_energy_kwh",
        "economic_usable_terminal_stored_energy_kwh",
        "schedule_deliverable_terminal_energy_kwh",
        "economic_deliverable_terminal_energy_kwh",
        "schedule_terminal_energy_value",
        "economic_terminal_energy_value",
        "delta_terminal_energy_value",
        "schedule_net_economic_cost",
        "economic_net_economic_cost",
        "delta_net_economic_cost",
        "schedule_grid_import_kwh",
        "economic_grid_import_kwh",
        "delta_grid_import_kwh",
        "schedule_grid_export_kwh",
        "economic_grid_export_kwh",
        "delta_grid_export_kwh",
        "schedule_absorbed_pv_surplus_kwh",
        "economic_absorbed_pv_surplus_kwh",
        "delta_absorbed_pv_surplus_kwh",
        "schedule_battery_throughput_kwh",
        "economic_battery_throughput_kwh",
        "delta_battery_throughput_kwh",
        "schedule_suppressed_grid_charge_kwh",
        "economic_suppressed_grid_charge_kwh",
    )
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(columns)
    for item in results:
        schedule = item.schedule
        economic = item.economic
        delta = item.deltas_economic_minus_schedule
        schedule_evidence = schedule.terminal_energy_value_evidence
        economic_evidence = economic.terminal_energy_value_evidence
        source = item.source_task_161_result
        writer.writerow(
            (
                source.scenario.scenario_id,
                _number(item.valuation_import_price),
                _number(schedule.economic_outcome_evidence.realized_import_cost),
                _number(economic.economic_outcome_evidence.realized_import_cost),
                _number(delta.realized_import_cost),
                _number(schedule.source_metrics.final_soc),
                _number(economic.source_metrics.final_soc),
                _number(delta.final_soc),
                _number(schedule_evidence.usable_terminal_stored_energy_kwh),
                _number(economic_evidence.usable_terminal_stored_energy_kwh),
                _number(schedule_evidence.deliverable_terminal_energy_kwh),
                _number(economic_evidence.deliverable_terminal_energy_kwh),
                _number(schedule_evidence.terminal_energy_value),
                _number(economic_evidence.terminal_energy_value),
                _number(delta.terminal_energy_value),
                _number(schedule.economic_outcome_evidence.net_economic_cost),
                _number(economic.economic_outcome_evidence.net_economic_cost),
                _number(delta.net_economic_cost),
                _number(schedule.source_metrics.grid_import_energy_kwh),
                _number(economic.source_metrics.grid_import_energy_kwh),
                _number(delta.grid_import_energy_kwh),
                _number(schedule.source_metrics.grid_export_energy_kwh),
                _number(economic.source_metrics.grid_export_energy_kwh),
                _number(delta.grid_export_energy_kwh),
                _number(schedule.source_metrics.absorbed_pv_surplus_kwh),
                _number(economic.source_metrics.absorbed_pv_surplus_kwh),
                _number(delta.absorbed_pv_surplus_kwh),
                _number(schedule.source_metrics.battery_throughput_kwh),
                _number(economic.source_metrics.battery_throughput_kwh),
                _number(delta.battery_throughput_kwh),
                _number(0.0),
                _number(
                    source.economic_evidence_metrics.economically_suppressed_grid_charge_energy_kwh
                ),
            )
        )
    return stream.getvalue()


def _daily_summary(results: tuple[TerminalValueEconomicScenarioResult, ...]) -> str:
    blocks = [
        "EOS Terminal-Value-Adjusted Economic Behavior Re-evaluation\n",
        "Terminal valuation rule: the maximum import price from the exact TASK-161 scenario tariff profile is applied equally to Schedule and Economic paths.\n",
        "This remains limited accounting: import cost minus assigned terminal energy value, not full profit.\n\n",
    ]
    for item in results:
        source = item.source_task_161_result
        schedule = item.schedule
        economic = item.economic
        delta = item.deltas_economic_minus_schedule
        classification = _classification(source)
        blocks.append(
            f"[{source.scenario.scenario_id}] classification={classification} valuation_import_price={_number(item.valuation_import_price)}\n"
            f"schedule: realized_import_cost={_number(schedule.economic_outcome_evidence.realized_import_cost)} terminal_soc={_number(schedule.source_metrics.final_soc)} terminal_value={_number(schedule.terminal_energy_value_evidence.terminal_energy_value)} net_economic_cost={_number(schedule.economic_outcome_evidence.net_economic_cost)}\n"
            f"economic: realized_import_cost={_number(economic.economic_outcome_evidence.realized_import_cost)} terminal_soc={_number(economic.source_metrics.final_soc)} terminal_value={_number(economic.terminal_energy_value_evidence.terminal_energy_value)} net_economic_cost={_number(economic.economic_outcome_evidence.net_economic_cost)}\n"
            f"economic_minus_schedule: realized_import_cost={_number(delta.realized_import_cost)} terminal_value={_number(delta.terminal_energy_value)} net_economic_cost={_number(delta.net_economic_cost)} grid_import_kwh={_number(delta.grid_import_energy_kwh)} grid_export_kwh={_number(delta.grid_export_energy_kwh)} absorbed_pv_surplus_kwh={_number(delta.absorbed_pv_surplus_kwh)} battery_throughput_kwh={_number(delta.battery_throughput_kwh)} final_soc={_number(delta.final_soc)}\n"
            f"interpretation: {_interpretation(item)}\n\n"
        )
    by_id = {item.source_task_161_result.scenario.scenario_id: item for item in results}
    blocks.extend(
        (
            "Answers:\n",
            f"1. E0 remains neutral: {_neutral(by_id['E0'])}.\n",
            f"2. E1 realized-cost advantage survives terminal-value adjustment: {_advantage(by_id['E1'])}.\n",
            f"3. E2 realized-cost advantage survives terminal-value adjustment: {_advantage(by_id['E2'])}.\n",
            f"4. TASK-161 conclusion materially changed: {_materially_changed(results)}.\n",
            f"5. Terminal-state valuation decision-relevant in these fixtures: {_decision_relevant(results)}.\n",
        )
    )
    return "".join(blocks)


def _classification(source: EconomicComparisonScenarioResult) -> str:
    metrics = source.economic_evidence_metrics
    if metrics.positive_cycles:
        return "positive"
    if metrics.negative_cycles:
        return "negative"
    if metrics.break_even_cycles:
        return "break_even"
    return "unavailable"


def _interpretation(item: TerminalValueEconomicScenarioResult) -> str:
    delta = item.deltas_economic_minus_schedule
    if delta.final_soc == 0.0:
        return (
            "Actual terminal SOC is equal, so equal valuation terms leave the net-cost "
            "delta equal to the realized-import-cost delta."
        )
    if delta.net_economic_cost < delta.realized_import_cost:
        return "Higher Economic terminal value strengthens its limited-accounting advantage."
    if delta.net_economic_cost > delta.realized_import_cost:
        return "Lower Economic terminal value reduces its realized-cost advantage."
    return "Terminal-state valuation does not change the realized-cost comparison."


def _neutral(item: TerminalValueEconomicScenarioResult) -> str:
    return str(
        item.deltas_economic_minus_schedule.realized_import_cost == 0.0
        and item.deltas_economic_minus_schedule.terminal_energy_value == 0.0
        and item.deltas_economic_minus_schedule.net_economic_cost == 0.0
    ).lower()


def _advantage(item: TerminalValueEconomicScenarioResult) -> str:
    return str(item.deltas_economic_minus_schedule.net_economic_cost < 0.0).lower()


def _materially_changed(
    results: tuple[TerminalValueEconomicScenarioResult, ...],
) -> str:
    return str(
        any(
            item.deltas_economic_minus_schedule.net_economic_cost
            != item.deltas_economic_minus_schedule.realized_import_cost
            for item in results
        )
    ).lower()


def _decision_relevant(results: tuple[TerminalValueEconomicScenarioResult, ...]) -> str:
    return str(
        any(
            item.deltas_economic_minus_schedule.terminal_energy_value != 0.0
            for item in results
        )
    ).lower()


def _paired_bar_svg(
    title: str,
    results: tuple[TerminalValueEconomicScenarioResult, ...],
    value_getter: Callable[[TerminalValueEconomicScenarioResult], tuple[float, float]],
) -> str:
    pairs = tuple(value_getter(item) for item in results)
    maximum = max(1.0, *(value for pair in pairs for value in pair))
    minimum = min(0.0, *(value for pair in pairs for value in pair))
    scale = max(maximum - minimum, 1.0)
    baseline = 255.0 - (0.0 - minimum) / scale * 210.0
    bars: list[str] = []
    for index, pair in enumerate(pairs):
        for offset, value in enumerate(pair):
            position = 255.0 - (value - minimum) / scale * 210.0
            bars.append(
                f'<rect x="{90 + index * 180 + offset * 36}" y="{min(position, baseline):.2f}" width="28" height="{abs(baseline - position):.2f}" fill="{("#2563eb", "#059669")[offset]}"/>'
            )
    labels = "".join(
        f'<text x="{90 + index * 180}" y="280" font-size="12">{item.source_task_161_result.scenario.scenario_id}</text>'
        for index, item in enumerate(results)
    )
    footer = (
        labels
        + '<text x="90" y="325" fill="#2563eb">Schedule</text><text x="180" y="325" fill="#059669">Economic</text>'
    )
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="360" viewBox="0 0 1024 360"><rect width="100%" height="100%" fill="white"/><text x="70" y="28" font-family="sans-serif" font-size="16">{title}</text><line x1="70" y1="{baseline:.2f}" x2="980" y2="{baseline:.2f}" stroke="#64748b"/>{"".join(bars)}{footer}</svg>\n'


def _number(value: float) -> str:
    return f"{value:.6f}"


if __name__ == "__main__":
    raise SystemExit(main())
