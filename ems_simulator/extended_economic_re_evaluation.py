# ruff: noqa: E501
"""TASK-172 fixed-control extended economic re-evaluation.

This read-model composition deliberately runs the established TASK-161 and
TASK-165 control paths once, then attaches accounting evidence to those fixed
traces.  Sensitivity assumptions never re-run a controller, optimizer, MPC
cycle, feasibility boundary, or simulator.
"""

import argparse
import csv
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from io import StringIO
from math import isclose
from pathlib import Path

from ems_simulator.economic_schedule_aware_comparison_demo import (
    DailyMetrics,
    EconomicComparisonScenarioResult,
    EconomicScheduleAwareComparisonResult,
    run_comparison,
)
from ems_simulator.terminal_soc_divergence_economic_demo import (
    TerminalSOCDivergenceResult,
    run_terminal_soc_divergence_evaluation,
)
from optimization import (
    BatteryDegradationCostEvidence,
    BatteryDegradationCostInput,
    BatteryOptimizationModel,
    DeterministicBatteryDegradationCostCalculator,
    DeterministicExportRevenueCalculator,
    DeterministicExtendedEconomicOutcomeCalculator,
    DeterministicTerminalEnergyValueCalculator,
    ExportRevenueEvidence,
    ExportRevenueInput,
    ExtendedEconomicOutcomeEvidence,
    ExtendedEconomicOutcomeInput,
    TerminalEnergyValueEvidence,
    TerminalEnergyValueInput,
)

_BASELINE_EXPORT_TARIFF = 0.20
_BASELINE_DEGRADATION_RATE = 0.05
_BASELINE_TERMINAL_VALUE = 0.85
_EXPORT_TARIFFS = (0.20, 0.60)
_DEGRADATION_RATES = (0.00, 0.05, 0.10)
_TERMINAL_VALUES = (0.00, 0.60, 0.85, 0.886427, 0.90)


@dataclass(frozen=True, slots=True)
class FixedControlPath:
    """One completed control trajectory; its observed metrics never mutate."""

    scenario_id: str
    path: str
    source_control_result: object
    source_metrics: DailyMetrics
    battery_model: BatteryOptimizationModel


@dataclass(frozen=True, slots=True)
class ExtendedEconomicEvaluation:
    """One accounting assumption tuple applied to one exact fixed trajectory."""

    fixed_path: FixedControlPath
    export_revenue_evidence: ExportRevenueEvidence
    battery_degradation_cost_evidence: BatteryDegradationCostEvidence
    terminal_energy_value_evidence: TerminalEnergyValueEvidence
    extended_outcome_evidence: ExtendedEconomicOutcomeEvidence

    def __post_init__(self) -> None:
        outcome = self.extended_outcome_evidence
        if (
            outcome.terminal_energy_value_evidence
            is not self.terminal_energy_value_evidence
        ):
            raise ValueError("extended outcome must retain exact terminal evidence")
        if (
            outcome.realized_export_revenue
            != self.export_revenue_evidence.realized_export_revenue
        ):
            raise ValueError("extended outcome must retain export evidence value")
        if (
            outcome.battery_degradation_cost
            != self.battery_degradation_cost_evidence.battery_degradation_cost
        ):
            raise ValueError("extended outcome must retain degradation evidence value")
        if (
            outcome.realized_import_cost
            != self.fixed_path.source_metrics.grid_import_cost
        ):
            raise ValueError(
                "extended outcome must retain existing interval import cost"
            )


@dataclass(frozen=True, slots=True)
class ExtendedEconomicReEvaluationResult:
    """All fixed paths, sensitivity evidence, and deterministic read-model files."""

    fixed_paths: tuple[FixedControlPath, ...]
    evaluations: tuple[ExtendedEconomicEvaluation, ...]
    scenario_summary_path: Path
    sensitivity_matrix_path: Path
    daily_summary_path: Path
    adjusted_net_cost_svg_path: Path
    component_svg_path: Path
    degradation_svg_path: Path
    export_tariff_svg_path: Path
    terminal_value_svg_path: Path


ComparisonRunner = Callable[[Path], EconomicScheduleAwareComparisonResult]
DivergenceRunner = Callable[[Path], TerminalSOCDivergenceResult]


def run_extended_economic_re_evaluation(
    output_directory: Path,
    comparison_runner: ComparisonRunner = run_comparison,
    divergence_runner: DivergenceRunner = run_terminal_soc_divergence_evaluation,
) -> ExtendedEconomicReEvaluationResult:
    """Evaluate complete accounting assumptions without re-running fixed controls.

    TASK-171 is intentionally not used to settle the three source scenarios:
    each has a time-varying import tariff and already owns a coherent interval
    realized-import-cost total.  Replacing it with a scalar tariff would change
    settlement semantics.  TASK-171 remains the scalar-settlement boundary for
    constant-tariff fixtures and direct TASK-163/TASK-168 compatibility.
    """

    if not isinstance(output_directory, Path):
        raise TypeError("output_directory must be a pathlib.Path")
    output_directory.mkdir(parents=True, exist_ok=True)
    fixed_paths = _fixed_control_paths(
        output_directory / "fixed_control_runs",
        comparison_runner,
        divergence_runner,
    )
    export_evidence, degradation_evidence, terminal_evidence = _evidence_caches(
        fixed_paths
    )
    evaluations = tuple(
        _evaluate_path(
            fixed_path,
            export_evidence[(index, export_tariff)],
            degradation_evidence[(index, degradation_rate)],
            terminal_evidence[(index, terminal_price)],
        )
        for index, fixed_path in enumerate(fixed_paths)
        for export_tariff in _EXPORT_TARIFFS
        for degradation_rate in _DEGRADATION_RATES
        for terminal_price in _TERMINAL_VALUES
    )
    scenario_summary_path = output_directory / "extended_economic_scenario_summary.csv"
    sensitivity_matrix_path = (
        output_directory / "extended_economic_sensitivity_matrix.csv"
    )
    daily_summary_path = output_directory / "evaluation_summary.txt"
    adjusted_net_cost_svg_path = output_directory / "adjusted_net_cost_by_scenario.svg"
    component_svg_path = (
        output_directory / "economic_component_waterfall_by_scenario.svg"
    )
    degradation_svg_path = output_directory / "degradation_sensitivity.svg"
    export_tariff_svg_path = output_directory / "export_tariff_sensitivity.svg"
    terminal_value_svg_path = (
        output_directory / "terminal_value_sensitivity_extended.svg"
    )
    scenario_summary_path.write_text(
        _summary_csv(evaluations), encoding="utf-8", newline=""
    )
    sensitivity_matrix_path.write_text(
        _matrix_csv(evaluations), encoding="utf-8", newline=""
    )
    daily_summary_path.write_text(
        _daily_summary(evaluations), encoding="utf-8", newline=""
    )
    baseline = _baseline_evaluations(evaluations)
    adjusted_net_cost_svg_path.write_text(
        _paired_svg("Baseline adjusted net economic cost", baseline, "cost"),
        encoding="utf-8",
    )
    component_svg_path.write_text(
        _paired_svg(
            "Baseline Economic minus Schedule components", baseline, "components"
        ),
        encoding="utf-8",
    )
    degradation_svg_path.write_text(
        _sensitivity_svg("Degradation-rate sensitivity", evaluations, "degradation"),
        encoding="utf-8",
    )
    export_tariff_svg_path.write_text(
        _sensitivity_svg("Export-tariff sensitivity", evaluations, "export"),
        encoding="utf-8",
    )
    terminal_value_svg_path.write_text(
        _sensitivity_svg("Terminal-value sensitivity", evaluations, "terminal"),
        encoding="utf-8",
    )
    return ExtendedEconomicReEvaluationResult(
        fixed_paths,
        evaluations,
        scenario_summary_path,
        sensitivity_matrix_path,
        daily_summary_path,
        adjusted_net_cost_svg_path,
        component_svg_path,
        degradation_svg_path,
        export_tariff_svg_path,
        terminal_value_svg_path,
    )


def _fixed_control_paths(
    output_directory: Path,
    comparison_runner: ComparisonRunner,
    divergence_runner: DivergenceRunner,
) -> tuple[FixedControlPath, ...]:
    """Run each reused source runner once, then retain exact result references."""

    comparison = comparison_runner(output_directory / "task161")
    by_id = {item.scenario.scenario_id: item for item in comparison.scenario_results}
    divergence = divergence_runner(output_directory / "task165")
    return (
        *_comparison_paths(by_id["E0"]),
        *_comparison_paths(by_id["E1"]),
        *_comparison_paths(by_id["E2"]),
        FixedControlPath(
            "C_TERMINAL_SOC_DIVERGENCE",
            "Schedule",
            divergence.schedule_result,
            divergence.schedule.source_metrics,
            divergence.schedule_input.daily_mpc_input.battery_optimization_model,
        ),
        FixedControlPath(
            "C_TERMINAL_SOC_DIVERGENCE",
            "Economic",
            divergence.economic_result,
            divergence.economic.source_metrics,
            divergence.economic_input.daily_mpc_input.battery_optimization_model,
        ),
    )


def _comparison_paths(
    result: EconomicComparisonScenarioResult,
) -> tuple[FixedControlPath, FixedControlPath]:
    model = result.schedule_input.daily_mpc_input.battery_optimization_model
    if result.economic_input.daily_mpc_input.battery_optimization_model is not model:
        raise ValueError("comparison paths must retain the exact same battery model")
    return (
        FixedControlPath(
            result.scenario.scenario_id,
            "Schedule",
            result.schedule_result,
            result.schedule_metrics,
            model,
        ),
        FixedControlPath(
            result.scenario.scenario_id,
            "Economic",
            result.economic_result,
            result.economic_metrics,
            model,
        ),
    )


def _evidence_caches(
    fixed_paths: tuple[FixedControlPath, ...],
) -> tuple[
    dict[tuple[int, float], ExportRevenueEvidence],
    dict[tuple[int, float], BatteryDegradationCostEvidence],
    dict[tuple[int, float], TerminalEnergyValueEvidence],
]:
    """Build each independent evidence item once per path and assumption."""

    export_calculator = DeterministicExportRevenueCalculator()
    degradation_calculator = DeterministicBatteryDegradationCostCalculator()
    terminal_calculator = DeterministicTerminalEnergyValueCalculator()
    export_evidence = {
        (index, export_tariff): export_calculator.calculate(
            ExportRevenueInput(
                fixed_path.source_metrics.grid_export_energy_kwh,
                export_tariff,
            )
        )
        for index, fixed_path in enumerate(fixed_paths)
        for export_tariff in _EXPORT_TARIFFS
    }
    degradation_evidence = {
        (index, degradation_rate): degradation_calculator.calculate(
            BatteryDegradationCostInput(
                fixed_path.source_metrics.battery_throughput_kwh,
                degradation_rate,
            )
        )
        for index, fixed_path in enumerate(fixed_paths)
        for degradation_rate in _DEGRADATION_RATES
    }
    terminal_evidence = {
        (index, terminal_price): terminal_calculator.calculate(
            TerminalEnergyValueInput(
                fixed_path.source_metrics.final_soc,
                fixed_path.battery_model,
                terminal_price,
            )
        )
        for index, fixed_path in enumerate(fixed_paths)
        for terminal_price in _TERMINAL_VALUES
    }
    return export_evidence, degradation_evidence, terminal_evidence


def _evaluate_path(
    fixed_path: FixedControlPath,
    export_evidence: ExportRevenueEvidence,
    degradation_evidence: BatteryDegradationCostEvidence,
    terminal_evidence: TerminalEnergyValueEvidence,
) -> ExtendedEconomicEvaluation:
    """Use precomputed evidence to aggregate one fixed trajectory combination."""

    metrics = fixed_path.source_metrics
    outcome = DeterministicExtendedEconomicOutcomeCalculator().calculate(
        ExtendedEconomicOutcomeInput(
            metrics.grid_import_cost,
            export_evidence.realized_export_revenue,
            degradation_evidence.battery_degradation_cost,
            terminal_evidence,
        )
    )
    return ExtendedEconomicEvaluation(
        fixed_path,
        export_evidence,
        degradation_evidence,
        terminal_evidence,
        outcome,
    )


def _baseline_evaluations(
    evaluations: tuple[ExtendedEconomicEvaluation, ...],
) -> tuple[ExtendedEconomicEvaluation, ...]:
    return tuple(
        evaluation
        for evaluation in evaluations
        if (
            evaluation.export_revenue_evidence.export_tariff_per_kwh
            == _BASELINE_EXPORT_TARIFF
            and evaluation.battery_degradation_cost_evidence.degradation_cost_per_throughput_kwh
            == _BASELINE_DEGRADATION_RATE
            and evaluation.terminal_energy_value_evidence.valuation_import_price
            == _BASELINE_TERMINAL_VALUE
        )
    )


def _pair_delta(
    schedule: ExtendedEconomicEvaluation,
    economic: ExtendedEconomicEvaluation,
) -> tuple[float, float, float, float, float]:
    """Return Economic minus Schedule, preserving TASK-168 component signs."""

    schedule_outcome = schedule.extended_outcome_evidence
    economic_outcome = economic.extended_outcome_evidence
    import_delta = (
        economic_outcome.realized_import_cost - schedule_outcome.realized_import_cost
    )
    export_delta = (
        economic_outcome.realized_export_revenue
        - schedule_outcome.realized_export_revenue
    )
    degradation_delta = (
        economic_outcome.battery_degradation_cost
        - schedule_outcome.battery_degradation_cost
    )
    terminal_delta = (
        economic_outcome.terminal_energy_value - schedule_outcome.terminal_energy_value
    )
    adjusted_delta = (
        economic_outcome.adjusted_net_economic_cost
        - schedule_outcome.adjusted_net_economic_cost
    )
    if not isclose(
        adjusted_delta,
        import_delta - export_delta + degradation_delta - terminal_delta,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError("Economic minus Schedule decomposition must balance")
    return import_delta, export_delta, degradation_delta, terminal_delta, adjusted_delta


def _pairs(
    evaluations: tuple[ExtendedEconomicEvaluation, ...],
) -> dict[
    tuple[str, float, float, float],
    tuple[ExtendedEconomicEvaluation, ExtendedEconomicEvaluation],
]:
    grouped: dict[
        tuple[str, float, float, float], dict[str, ExtendedEconomicEvaluation]
    ] = {}
    for evaluation in evaluations:
        key = (
            evaluation.fixed_path.scenario_id,
            evaluation.export_revenue_evidence.export_tariff_per_kwh,
            evaluation.battery_degradation_cost_evidence.degradation_cost_per_throughput_kwh,
            evaluation.terminal_energy_value_evidence.valuation_import_price,
        )
        grouped.setdefault(key, {})[evaluation.fixed_path.path] = evaluation
    return {
        key: (paths["Schedule"], paths["Economic"]) for key, paths in grouped.items()
    }


def _summary_csv(evaluations: tuple[ExtendedEconomicEvaluation, ...]) -> str:
    return _csv(evaluation for evaluation in _baseline_evaluations(evaluations))


def _matrix_csv(evaluations: tuple[ExtendedEconomicEvaluation, ...]) -> str:
    return _csv(evaluations)


def _csv(rows: Iterable[ExtendedEconomicEvaluation]) -> str:
    evaluations: tuple[ExtendedEconomicEvaluation, ...] = tuple(rows)
    pair_map = _pairs(evaluations)
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        (
            "scenario_id",
            "path",
            "realized_import_energy_kwh",
            "realized_import_cost",
            "realized_export_energy_kwh",
            "export_tariff_per_kwh",
            "realized_export_revenue",
            "battery_throughput_kwh",
            "degradation_cost_per_throughput_kwh",
            "battery_degradation_cost",
            "final_soc_fraction",
            "deliverable_terminal_energy_kwh",
            "terminal_valuation_price",
            "terminal_energy_value",
            "adjusted_net_economic_cost",
            "economic_minus_schedule_delta_import_cost",
            "economic_minus_schedule_delta_export_revenue",
            "economic_minus_schedule_delta_degradation_cost",
            "economic_minus_schedule_delta_terminal_value",
            "economic_minus_schedule_adjusted_cost",
        )
    )
    for evaluation in evaluations:
        metrics = evaluation.fixed_path.source_metrics
        export = evaluation.export_revenue_evidence
        degradation = evaluation.battery_degradation_cost_evidence
        terminal = evaluation.terminal_energy_value_evidence
        outcome = evaluation.extended_outcome_evidence
        key = (
            evaluation.fixed_path.scenario_id,
            export.export_tariff_per_kwh,
            degradation.degradation_cost_per_throughput_kwh,
            terminal.valuation_import_price,
        )
        delta = _pair_delta(*pair_map[key])
        writer.writerow(
            (
                evaluation.fixed_path.scenario_id,
                evaluation.fixed_path.path,
                _number(metrics.grid_import_energy_kwh),
                _number(outcome.realized_import_cost),
                _number(metrics.grid_export_energy_kwh),
                _number(export.export_tariff_per_kwh),
                _number(export.realized_export_revenue),
                _number(metrics.battery_throughput_kwh),
                _number(degradation.degradation_cost_per_throughput_kwh),
                _number(degradation.battery_degradation_cost),
                _number(metrics.final_soc),
                _number(terminal.deliverable_terminal_energy_kwh),
                _number(terminal.valuation_import_price),
                _number(terminal.terminal_energy_value),
                _number(outcome.adjusted_net_economic_cost),
                *(_number(value) for value in delta),
            )
        )
    return stream.getvalue()


def _daily_summary(evaluations: tuple[ExtendedEconomicEvaluation, ...]) -> str:
    baseline_pairs = _pairs(_baseline_evaluations(evaluations))
    lines = [
        "EOS Extended Economic Scenario Re-evaluation",
        "fixed_control=true: TASK-161 E0/E1/E2 and TASK-165 paths each ran once before accounting sensitivities.",
        "throughput_basis=existing DailyMetrics.battery_throughput_kwh (sum(abs(actual battery power) * step duration)).",
        "import_cost=existing interval-realized import settlement; TASK-171 scalar settlement is not used for variable-Tou profiles.",
        f"export_tariffs={','.join(_number(value) for value in _EXPORT_TARIFFS)} degradation_rates={','.join(_number(value) for value in _DEGRADATION_RATES)} terminal_values={','.join(_number(value) for value in _TERMINAL_VALUES)}",
    ]
    for key, (schedule, economic) in baseline_pairs.items():
        (
            import_delta,
            export_delta,
            degradation_delta,
            terminal_delta,
            adjusted_delta,
        ) = _pair_delta(schedule, economic)
        dominant_name, dominant_value = max(
            (
                ("import", import_delta),
                ("export", -export_delta),
                ("degradation", degradation_delta),
                ("terminal", -terminal_delta),
            ),
            key=lambda item: abs(item[1]),
        )
        lines.append(
            f"{key[0]} baseline economic_minus_schedule: import={_number(import_delta)} export={_number(export_delta)} degradation={_number(degradation_delta)} terminal={_number(terminal_delta)} adjusted={_number(adjusted_delta)}; lower adjusted cost is better."
        )
        lines.append(
            f"{key[0]} dominant adjusted-cost contribution={dominant_name}:{_number(dominant_value)}."
        )
    ranking_changes = _ranking_changes(evaluations)
    lines.extend(
        (
            f"Q1 export revenue ranking changes observed={str(ranking_changes['export']).lower()}.",
            f"Q2 degradation ranking changes observed={str(ranking_changes['degradation']).lower()}.",
            f"Q3 terminal valuation ranking changes observed={str(ranking_changes['terminal']).lower()}; C retains terminal-SOC divergence evidence.",
            "Q4 TASK-161/164/165/166 conclusions are re-evaluated under export and degradation terms; these are fixed-trajectory accounting results, not cash profit or control objectives.",
            "Q5 component deltas are explicit in the sensitivity matrix; no component is inferred from a rerun trajectory.",
        )
    )
    return "\n".join(lines) + "\n"


def _ranking_changes(
    evaluations: tuple[ExtendedEconomicEvaluation, ...],
) -> dict[str, bool]:
    changes: dict[str, bool] = {}
    for name in ("export", "degradation", "terminal"):
        groups: dict[tuple[str, float, float], set[int]] = {}
        for key, pair in _pairs(evaluations).items():
            scenario_id, export_tariff, degradation_rate, terminal_price = key
            fixed_assumptions = (
                (scenario_id, degradation_rate, terminal_price)
                if name == "export"
                else (scenario_id, export_tariff, terminal_price)
                if name == "degradation"
                else (scenario_id, export_tariff, degradation_rate)
            )
            delta = _pair_delta(*pair)[4]
            groups.setdefault(fixed_assumptions, set()).add(
                (delta > 0.0) - (delta < 0.0)
            )
        changes[name] = any(len(signs) > 1 for signs in groups.values())
    return changes


def _paired_svg(
    title: str,
    baseline: tuple[ExtendedEconomicEvaluation, ...],
    kind: str,
) -> str:
    pairs = _pairs(baseline)
    labels = tuple(pairs)
    if kind == "cost":
        values = tuple(
            (
                schedule.extended_outcome_evidence.adjusted_net_economic_cost,
                economic.extended_outcome_evidence.adjusted_net_economic_cost,
            )
            for schedule, economic in pairs.values()
        )
    else:
        values = tuple(
            (_pair_delta(schedule, economic)[0], _pair_delta(schedule, economic)[4])
            for schedule, economic in pairs.values()
        )
    return _bar_svg(title, labels, values)


def _sensitivity_svg(
    title: str,
    evaluations: tuple[ExtendedEconomicEvaluation, ...],
    dimension: str,
) -> str:
    baseline_export = _BASELINE_EXPORT_TARIFF
    baseline_degradation = _BASELINE_DEGRADATION_RATE
    baseline_terminal = _BASELINE_TERMINAL_VALUE
    filtered = tuple(
        evaluation
        for evaluation in evaluations
        if _matches_sensitivity(
            evaluation,
            dimension,
            baseline_export,
            baseline_degradation,
            baseline_terminal,
        )
    )
    pairs = _pairs(filtered)
    labels = tuple(
        f"{key[0]}:{_number(_dimension_value(key, dimension))}" for key in pairs
    )
    values = tuple((_pair_delta(*pair)[4], 0.0) for pair in pairs.values())
    return _bar_svg(title, labels, values)


def _matches_sensitivity(
    evaluation: ExtendedEconomicEvaluation,
    dimension: str,
    baseline_export: float,
    baseline_degradation: float,
    baseline_terminal: float,
) -> bool:
    if dimension == "export":
        return (
            evaluation.battery_degradation_cost_evidence.degradation_cost_per_throughput_kwh
            == baseline_degradation
            and evaluation.terminal_energy_value_evidence.valuation_import_price
            == baseline_terminal
        )
    if dimension == "degradation":
        return (
            evaluation.export_revenue_evidence.export_tariff_per_kwh == baseline_export
            and evaluation.terminal_energy_value_evidence.valuation_import_price
            == baseline_terminal
        )
    if dimension == "terminal":
        return (
            evaluation.export_revenue_evidence.export_tariff_per_kwh == baseline_export
            and evaluation.battery_degradation_cost_evidence.degradation_cost_per_throughput_kwh
            == baseline_degradation
        )
    raise ValueError("dimension must be export, degradation, or terminal")


def _dimension_value(key: tuple[str, float, float, float], dimension: str) -> float:
    if dimension == "export":
        return key[1]
    if dimension == "degradation":
        return key[2]
    if dimension == "terminal":
        return key[3]
    raise ValueError("dimension must be export, degradation, or terminal")


def _bar_svg(
    title: str, labels: Sequence[object], values: Sequence[tuple[float, float]]
) -> str:
    flat = tuple(value for pair in values for value in pair)
    maximum, minimum = max(1.0, *flat), min(0.0, *flat)
    scale = max(maximum - minimum, 1.0)
    baseline = 255.0 - (0.0 - minimum) / scale * 190.0
    bars = "".join(
        f'<rect x="{70 + index * 70 + side * 28}" y="{min(baseline, 255.0 - (value - minimum) / scale * 190.0):.2f}" width="20" height="{abs(baseline - (255.0 - (value - minimum) / scale * 190.0)):.2f}" fill="{("#2563eb", "#059669")[side]}"/>'
        for index, pair in enumerate(values)
        for side, value in enumerate(pair)
    )
    text = "".join(
        f'<text x="{70 + index * 70}" y="290" font-size="9">{label}</text>'
        for index, label in enumerate(labels)
    )
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="330" viewBox="0 0 1024 330"><rect width="100%" height="100%" fill="white"/><text x="40" y="28" font-family="sans-serif" font-size="16">{title}</text><line x1="40" y1="{baseline:.2f}" x2="990" y2="{baseline:.2f}" stroke="#64748b"/>{bars}{text}<text x="40" y="315" fill="#2563eb">blue=Schedule / delta</text><text x="220" y="315" fill="#059669">green=Economic / zero</text></svg>\n'


def _number(value: float) -> str:
    return f"{value:.6f}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="EOS TASK-172 fixed-control extended economic re-evaluation"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("simulation_output_task172_extended_economic"),
    )
    arguments = parser.parse_args(argv)
    result = run_extended_economic_re_evaluation(arguments.output_dir)
    for path in (
        result.scenario_summary_path,
        result.sensitivity_matrix_path,
        result.daily_summary_path,
        result.adjusted_net_cost_svg_path,
        result.component_svg_path,
        result.degradation_svg_path,
        result.export_tariff_svg_path,
        result.terminal_value_svg_path,
    ):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
