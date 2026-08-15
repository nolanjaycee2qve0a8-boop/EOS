# ruff: noqa: E501
"""Evaluate terminal-value accounting robustness across fixed control outcomes.

TASK-167 composes only existing TASK-165 control paths and TASK-162/163
accounting evidence.  Each scenario's Schedule-aware and Economic
Schedule-aware trajectories run once; terminal valuation prices then vary only
post-run accounting evidence.  No control, planning, MPC, feasibility,
actuation, or Simulator semantic is changed here.
"""

import argparse
import csv
from collections.abc import Sequence
from dataclasses import dataclass
from io import StringIO
from itertools import pairwise
from pathlib import Path

from ems_simulator.economic_multi_opportunity_explainable_mpc_daily import (
    EconomicMultiOpportunityExplainableMPCDailySimulationResult,
)
from ems_simulator.economic_schedule_aware_comparison_demo import (
    DailyMetrics,
    _daily_metrics,
    _economic_runner,
    _schedule_runner,
)
from ems_simulator.multi_opportunity_explainable_mpc_daily import (
    MultiOpportunityExplainableMPCDailySimulationInput,
    MultiOpportunityExplainableMPCDailySimulationResult,
)
from ems_simulator.terminal_soc_divergence_economic_demo import (
    TerminalSOCDivergenceScenario,
    _inputs,
)
from ems_simulator.terminal_valuation_sensitivity_demo import (
    TerminalValuationBreakEvenEvidence,
    TerminalValuationRanking,
)
from optimization import (
    BatteryOptimizationModel,
    DeterministicEconomicOutcomeCalculator,
    DeterministicTerminalEnergyValueCalculator,
    EconomicOutcomeBoundary,
    EconomicOutcomeEvidence,
    EconomicOutcomeInput,
    NetLoadAwareBaselineOptimizationConfiguration,
    TerminalEnergyValueBoundary,
    TerminalEnergyValueEvidence,
    TerminalEnergyValueInput,
)

_FLOAT_TOLERANCE = 1e-9
_BREAK_EVEN_SAMPLE_OFFSET = 0.000001
_REQUIRED_VALUATION_PRICES = (0.00, 0.40, 0.60, 0.75, 0.80, 0.85, 0.90, 1.00, 1.20)


@dataclass(frozen=True, slots=True)
class TerminalValueRobustnessScenario:
    """Caller-owned structural facts; no expected winner is encoded."""

    scenario_id: str
    description: str
    control_scenario: TerminalSOCDivergenceScenario

    def __post_init__(self) -> None:
        if not isinstance(self.scenario_id, str) or not self.scenario_id:
            raise ValueError("scenario_id must be a non-empty str")
        if not isinstance(self.description, str) or not self.description:
            raise ValueError("description must be a non-empty str")
        if not isinstance(self.control_scenario, TerminalSOCDivergenceScenario):
            raise TypeError("control_scenario must be a TerminalSOCDivergenceScenario")


@dataclass(frozen=True, slots=True)
class TerminalValueRobustnessFixedControlResult:
    """Exact completed paths and zero-price evidence used to derive thresholds."""

    scenario: TerminalValueRobustnessScenario
    schedule_input: MultiOpportunityExplainableMPCDailySimulationInput
    economic_input: MultiOpportunityExplainableMPCDailySimulationInput
    schedule_result: MultiOpportunityExplainableMPCDailySimulationResult
    economic_result: EconomicMultiOpportunityExplainableMPCDailySimulationResult
    schedule_metrics: DailyMetrics
    economic_metrics: DailyMetrics
    schedule_zero_terminal_evidence: TerminalEnergyValueEvidence
    economic_zero_terminal_evidence: TerminalEnergyValueEvidence
    break_even_evidence: TerminalValuationBreakEvenEvidence
    delta_realized_import_cost: float
    delta_final_soc: float
    delta_deliverable_terminal_energy_kwh: float

    def __post_init__(self) -> None:
        if not isinstance(self.scenario, TerminalValueRobustnessScenario):
            raise TypeError("scenario must be a TerminalValueRobustnessScenario")
        if not isinstance(
            self.schedule_input,
            MultiOpportunityExplainableMPCDailySimulationInput,
        ) or not isinstance(
            self.economic_input,
            MultiOpportunityExplainableMPCDailySimulationInput,
        ):
            raise TypeError(
                "inputs must be MultiOpportunityExplainableMPCDailySimulationInput"
            )
        if not isinstance(
            self.schedule_result,
            MultiOpportunityExplainableMPCDailySimulationResult,
        ) or not isinstance(
            self.economic_result,
            EconomicMultiOpportunityExplainableMPCDailySimulationResult,
        ):
            raise TypeError("results must preserve existing daily runner types")
        if not isinstance(self.schedule_metrics, DailyMetrics) or not isinstance(
            self.economic_metrics,
            DailyMetrics,
        ):
            raise TypeError("metrics must be DailyMetrics")
        if not isinstance(
            self.schedule_zero_terminal_evidence,
            TerminalEnergyValueEvidence,
        ) or not isinstance(
            self.economic_zero_terminal_evidence,
            TerminalEnergyValueEvidence,
        ):
            raise TypeError(
                "zero terminal evidence must be TerminalEnergyValueEvidence"
            )
        if not isinstance(self.break_even_evidence, TerminalValuationBreakEvenEvidence):
            raise TypeError(
                "break_even_evidence must be TerminalValuationBreakEvenEvidence"
            )
        schedule_model = self.schedule_input.daily_mpc_input.battery_optimization_model
        economic_model = self.economic_input.daily_mpc_input.battery_optimization_model
        if economic_model is not schedule_model:
            raise ValueError("both paths must preserve exact battery model identity")
        for evidence, metrics in (
            (self.schedule_zero_terminal_evidence, self.schedule_metrics),
            (self.economic_zero_terminal_evidence, self.economic_metrics),
        ):
            if evidence.source_input.battery_model is not schedule_model:
                raise ValueError("terminal evidence must preserve exact battery model")
            if evidence.source_input.terminal_soc != metrics.final_soc:
                raise ValueError("terminal evidence must preserve actual final SOC")
            if evidence.source_input.valuation_import_price != 0.0:
                raise ValueError("fixed control evidence must use zero valuation price")
        expected_cost_delta = (
            self.economic_metrics.grid_import_cost
            - self.schedule_metrics.grid_import_cost
        )
        expected_soc_delta = (
            self.economic_metrics.final_soc - self.schedule_metrics.final_soc
        )
        expected_energy_delta = (
            self.economic_zero_terminal_evidence.deliverable_terminal_energy_kwh
            - self.schedule_zero_terminal_evidence.deliverable_terminal_energy_kwh
        )
        if self.delta_realized_import_cost != expected_cost_delta:
            raise ValueError("realized-cost delta must retain exact actual metrics")
        if self.delta_final_soc != expected_soc_delta:
            raise ValueError("final-SOC delta must retain exact actual metrics")
        if self.delta_deliverable_terminal_energy_kwh != expected_energy_delta:
            raise ValueError("deliverable-energy delta must retain TASK-162 evidence")
        if self.break_even_evidence.delta_realized_import_cost != expected_cost_delta:
            raise ValueError("break-even cost delta must preserve actual metrics")
        if (
            self.break_even_evidence.delta_deliverable_terminal_energy_kwh
            != expected_energy_delta
        ):
            raise ValueError("break-even energy delta must preserve TASK-162 evidence")

    @property
    def realized_cost_difference_per_extra_deliverable_kwh(self) -> float | None:
        """Return the positive ratio only when terminal-energy divergence exists."""

        if abs(self.delta_deliverable_terminal_energy_kwh) <= _FLOAT_TOLERANCE:
            return None
        return abs(self.delta_realized_import_cost) / abs(
            self.delta_deliverable_terminal_energy_kwh
        )


@dataclass(frozen=True, slots=True)
class TerminalValueRobustnessPoint:
    """Exact TASK-162/163 evidence for one fixed scenario and valuation point."""

    source_fixed_control_result: TerminalValueRobustnessFixedControlResult
    scenario_id: str
    valuation_import_price: float
    schedule_terminal_energy_value_evidence: TerminalEnergyValueEvidence
    schedule_economic_outcome_evidence: EconomicOutcomeEvidence
    economic_terminal_energy_value_evidence: TerminalEnergyValueEvidence
    economic_economic_outcome_evidence: EconomicOutcomeEvidence
    delta_terminal_energy_value: float
    delta_net_economic_cost: float
    ranking: TerminalValuationRanking

    def __post_init__(self) -> None:
        if not isinstance(
            self.source_fixed_control_result,
            TerminalValueRobustnessFixedControlResult,
        ):
            raise TypeError(
                "source_fixed_control_result must be a fixed control result"
            )
        if self.scenario_id != self.source_fixed_control_result.scenario.scenario_id:
            raise ValueError("scenario_id must preserve exact fixed result semantics")
        price = _non_negative(self.valuation_import_price, "valuation_import_price")
        evidence = (
            self.schedule_terminal_energy_value_evidence,
            self.economic_terminal_energy_value_evidence,
        )
        outcomes = (
            self.schedule_economic_outcome_evidence,
            self.economic_economic_outcome_evidence,
        )
        if not all(isinstance(item, TerminalEnergyValueEvidence) for item in evidence):
            raise TypeError("terminal evidence must be TerminalEnergyValueEvidence")
        if not all(isinstance(item, EconomicOutcomeEvidence) for item in outcomes):
            raise TypeError("outcomes must be EconomicOutcomeEvidence")
        fixed = self.source_fixed_control_result
        model = fixed.schedule_input.daily_mpc_input.battery_optimization_model
        for item, metrics in (
            (self.schedule_terminal_energy_value_evidence, fixed.schedule_metrics),
            (self.economic_terminal_energy_value_evidence, fixed.economic_metrics),
        ):
            if item.source_input.battery_model is not model:
                raise ValueError("point must preserve exact battery model identity")
            if item.source_input.terminal_soc != metrics.final_soc:
                raise ValueError("point must preserve fixed actual final SOC")
            if item.source_input.valuation_import_price != price:
                raise ValueError(
                    "point terminal evidence must preserve its valuation price"
                )
        if (
            self.schedule_economic_outcome_evidence.terminal_energy_value_evidence
            is not self.schedule_terminal_energy_value_evidence
        ) or (
            self.economic_economic_outcome_evidence.terminal_energy_value_evidence
            is not self.economic_terminal_energy_value_evidence
        ):
            raise ValueError("outcomes must preserve exact terminal evidence identity")
        expected_terminal_delta = (
            self.economic_terminal_energy_value_evidence.terminal_energy_value
            - self.schedule_terminal_energy_value_evidence.terminal_energy_value
        )
        expected_net_delta = (
            self.economic_economic_outcome_evidence.net_economic_cost
            - self.schedule_economic_outcome_evidence.net_economic_cost
        )
        if self.delta_terminal_energy_value != expected_terminal_delta:
            raise ValueError("terminal-value delta must preserve source evidence")
        if self.delta_net_economic_cost != expected_net_delta:
            raise ValueError("net-cost delta must preserve source evidence")
        if not isinstance(self.ranking, TerminalValuationRanking):
            raise TypeError("ranking must be a TerminalValuationRanking")
        if self.ranking is not _ranking(expected_net_delta):
            raise ValueError(
                "ranking must follow Economic minus Schedule sign semantics"
            )
        object.__setattr__(self, "valuation_import_price", price)


@dataclass(frozen=True, slots=True)
class TerminalValueRobustnessMatrixResult:
    """Ordered fixed controls, accounting matrix points, and emitted artifacts."""

    fixed_control_results: tuple[TerminalValueRobustnessFixedControlResult, ...]
    sensitivity_points: tuple[TerminalValueRobustnessPoint, ...]
    scenario_summary_csv_path: Path
    matrix_csv_path: Path
    evaluation_summary_path: Path
    break_even_svg_path: Path
    terminal_soc_delta_svg_path: Path
    cost_energy_delta_svg_path: Path
    net_cost_delta_heatmap_svg_path: Path

    def __post_init__(self) -> None:
        if (
            not isinstance(self.fixed_control_results, tuple)
            or len(self.fixed_control_results) < 3
        ):
            raise ValueError(
                "fixed_control_results must contain at least three scenarios"
            )
        if not all(
            isinstance(item, TerminalValueRobustnessFixedControlResult)
            for item in self.fixed_control_results
        ):
            raise TypeError("fixed_control_results contain invalid values")
        identifiers = tuple(
            item.scenario.scenario_id for item in self.fixed_control_results
        )
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("scenario IDs must be unique")
        if (
            not isinstance(self.sensitivity_points, tuple)
            or not self.sensitivity_points
        ):
            raise ValueError("sensitivity_points must be a non-empty tuple")
        if not all(
            isinstance(item, TerminalValueRobustnessPoint)
            for item in self.sensitivity_points
        ):
            raise TypeError("sensitivity_points contain invalid values")
        ordered_ids = tuple(point.scenario_id for point in self.sensitivity_points)
        positions = tuple(identifiers.index(identifier) for identifier in ordered_ids)
        if any(left > right for left, right in pairwise(positions)):
            raise ValueError("sensitivity points must retain scenario order")
        for fixed in self.fixed_control_results:
            points = self.points_for(fixed.scenario.scenario_id)
            if not points:
                raise ValueError(
                    "each fixed control result requires sensitivity points"
                )
            prices = tuple(point.valuation_import_price for point in points)
            if any(left >= right for left, right in pairwise(prices)):
                raise ValueError(
                    "sensitivity prices must be strictly ordered per scenario"
                )
            if any(point.source_fixed_control_result is not fixed for point in points):
                raise ValueError(
                    "points must preserve exact fixed control result identity"
                )
        if not all(isinstance(path, Path) for path in self.output_paths):
            raise TypeError("output paths must be pathlib.Path instances")

    def points_for(self, scenario_id: str) -> tuple[TerminalValueRobustnessPoint, ...]:
        """Return one scenario's points while preserving global caller order."""

        return tuple(
            point
            for point in self.sensitivity_points
            if point.scenario_id == scenario_id
        )

    @property
    def output_paths(self) -> tuple[Path, ...]:
        return (
            self.scenario_summary_csv_path,
            self.matrix_csv_path,
            self.evaluation_summary_path,
            self.break_even_svg_path,
            self.terminal_soc_delta_svg_path,
            self.cost_energy_delta_svg_path,
            self.net_cost_delta_heatmap_svg_path,
        )


@dataclass(frozen=True, slots=True)
class _CompletedControlPaths:
    """Private exact completed runner outputs before valuation post-processing."""

    scenario: TerminalValueRobustnessScenario
    schedule_input: MultiOpportunityExplainableMPCDailySimulationInput
    economic_input: MultiOpportunityExplainableMPCDailySimulationInput
    schedule_result: MultiOpportunityExplainableMPCDailySimulationResult
    economic_result: EconomicMultiOpportunityExplainableMPCDailySimulationResult
    schedule_metrics: DailyMetrics
    economic_metrics: DailyMetrics


def scenario_matrix() -> tuple[TerminalValueRobustnessScenario, ...]:
    """Return R1/R2/R3 with increasing natural actual terminal-SOC divergence.

    All cases retain 0.95 charge/discharge efficiency, weak PV at or below
    load, and a later 0.85 import price.  R1/R2 vary early negative-margin
    price and the number of caller-owned eligible cheap intervals; R3 is the
    frozen TASK-165 baseline itself.
    """

    return (
        _scenario(
            "R1_SMALL",
            "One 0.79-price eligible grid-charge interval at 1.5 kW; weak later PV does not erase the actual SOC divergence.",
            1,
            0.79,
            1.5,
        ),
        _scenario(
            "R2_MEDIUM",
            "Two 0.81-price eligible grid-charge intervals at 1.5 kW; weak later PV does not erase the actual SOC divergence.",
            2,
            0.81,
            1.5,
        ),
        _scenario(
            "R3_LARGE_TASK165_BASELINE",
            "Frozen TASK-165 mechanism: six 0.80-price eligible intervals at 3.0 kW, bounded PV, and terminal SOC divergence.",
            6,
            0.80,
            3.0,
        ),
    )


def run_terminal_value_robustness_matrix(
    output_directory: Path,
    terminal_value_calculator: TerminalEnergyValueBoundary | None = None,
    outcome_calculator: EconomicOutcomeBoundary | None = None,
) -> TerminalValueRobustnessMatrixResult:
    """Run each scenario's controls once and evaluate only accounting per price."""

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
    fixed_results: list[TerminalValueRobustnessFixedControlResult] = []
    all_points: list[TerminalValueRobustnessPoint] = []
    for scenario in scenario_matrix():
        completed = _run_fixed_control(
            scenario, output_directory / scenario.scenario_id
        )
        schedule_zero = _terminal_and_outcome(
            completed.schedule_metrics,
            completed.schedule_input.daily_mpc_input.battery_optimization_model,
            0.0,
            terminal_calculator,
            net_cost_calculator,
        )
        economic_zero = _terminal_and_outcome(
            completed.economic_metrics,
            completed.economic_input.daily_mpc_input.battery_optimization_model,
            0.0,
            terminal_calculator,
            net_cost_calculator,
        )
        fixed = _fixed_result(completed, schedule_zero[0], economic_zero[0])
        fixed_results.append(fixed)
        prices = _scenario_prices(fixed.break_even_evidence)
        points = [
            _point_from_evidence(
                fixed,
                0.0,
                schedule_zero,
                economic_zero,
            )
        ]
        for price in prices:
            if price == 0.0:
                continue
            points.append(
                _evaluate_point(
                    fixed,
                    price,
                    terminal_calculator,
                    net_cost_calculator,
                )
            )
        all_points.extend(points)

    fixed_tuple = tuple(fixed_results)
    point_tuple = tuple(all_points)
    scenario_summary_csv_path = output_directory / "robustness_scenario_summary.csv"
    matrix_csv_path = output_directory / "terminal_value_robustness_matrix.csv"
    evaluation_summary_path = output_directory / "evaluation_summary.txt"
    break_even_svg_path = output_directory / "break_even_price_by_scenario.svg"
    terminal_soc_delta_svg_path = (
        output_directory / "terminal_soc_delta_by_scenario.svg"
    )
    cost_energy_delta_svg_path = (
        output_directory / "realized_cost_vs_terminal_energy_delta.svg"
    )
    net_cost_delta_heatmap_svg_path = output_directory / "net_cost_delta_heatmap.svg"
    result = TerminalValueRobustnessMatrixResult(
        fixed_tuple,
        point_tuple,
        scenario_summary_csv_path,
        matrix_csv_path,
        evaluation_summary_path,
        break_even_svg_path,
        terminal_soc_delta_svg_path,
        cost_energy_delta_svg_path,
        net_cost_delta_heatmap_svg_path,
    )
    scenario_summary_csv_path.write_text(
        _scenario_summary_csv(result), encoding="utf-8", newline=""
    )
    matrix_csv_path.write_text(_matrix_csv(result), encoding="utf-8", newline="")
    evaluation_summary_path.write_text(
        _evaluation_summary(result), encoding="utf-8", newline=""
    )
    break_even_svg_path.write_text(_break_even_svg(result), encoding="utf-8")
    terminal_soc_delta_svg_path.write_text(_soc_delta_svg(result), encoding="utf-8")
    cost_energy_delta_svg_path.write_text(_cost_energy_svg(result), encoding="utf-8")
    net_cost_delta_heatmap_svg_path.write_text(_heatmap_svg(result), encoding="utf-8")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    """Run the deterministic TASK-167 CLI."""

    parser = argparse.ArgumentParser(
        description="EOS TASK-167 terminal value robustness matrix"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("simulation_output_task167_terminal_value_robustness"),
    )
    arguments = parser.parse_args(argv)
    result = run_terminal_value_robustness_matrix(arguments.output_dir)
    for path in result.output_paths:
        print(path)
    return 0


def _scenario(
    scenario_id: str,
    description: str,
    early_hours: int,
    early_price: float,
    grid_charge_power_kw: float,
) -> TerminalValueRobustnessScenario:
    configuration = NetLoadAwareBaselineOptimizationConfiguration(
        early_price,
        1.00,
        grid_charge_power_kw,
    )
    control = TerminalSOCDivergenceScenario(
        description,
        0.50,
        0.60,
        (early_price,) * early_hours + (0.85,) * (24 - early_hours),
        configuration,
    )
    return TerminalValueRobustnessScenario(scenario_id, description, control)


def _run_fixed_control(
    scenario: TerminalValueRobustnessScenario,
    output_directory: Path,
) -> _CompletedControlPaths:
    """Execute the existing two daily runners exactly once for this scenario."""

    output_directory.mkdir(parents=True, exist_ok=True)
    schedule_input, economic_input = _inputs(
        scenario.control_scenario, output_directory
    )
    configuration = scenario.control_scenario.candidate_configuration
    schedule_result = _schedule_runner(configuration).run(schedule_input)
    economic_result = _economic_runner(configuration).run(economic_input)
    return _CompletedControlPaths(
        scenario,
        schedule_input,
        economic_input,
        schedule_result,
        economic_result,
        _daily_metrics(schedule_result),
        _daily_metrics(economic_result),
    )


def _terminal_and_outcome(
    metrics: DailyMetrics,
    battery_model: BatteryOptimizationModel,
    price: float,
    terminal_calculator: TerminalEnergyValueBoundary,
    outcome_calculator: EconomicOutcomeBoundary,
) -> tuple[TerminalEnergyValueEvidence, EconomicOutcomeEvidence]:
    """Build exactly one TASK-162 and one TASK-163 evidence pair per path/point."""

    terminal = terminal_calculator.calculate(
        TerminalEnergyValueInput(metrics.final_soc, battery_model, price)
    )
    outcome = outcome_calculator.calculate(
        EconomicOutcomeInput(metrics.grid_import_cost, terminal)
    )
    return (terminal, outcome)


def _fixed_result(
    completed: _CompletedControlPaths,
    schedule_zero: TerminalEnergyValueEvidence,
    economic_zero: TerminalEnergyValueEvidence,
) -> TerminalValueRobustnessFixedControlResult:
    delta_cost = (
        completed.economic_metrics.grid_import_cost
        - completed.schedule_metrics.grid_import_cost
    )
    delta_soc = (
        completed.economic_metrics.final_soc - completed.schedule_metrics.final_soc
    )
    delta_energy = (
        economic_zero.deliverable_terminal_energy_kwh
        - schedule_zero.deliverable_terminal_energy_kwh
    )
    available = abs(delta_energy) > _FLOAT_TOLERANCE
    break_even = TerminalValuationBreakEvenEvidence(
        delta_cost,
        delta_energy,
        None if not available else delta_cost / delta_energy,
        available,
    )
    return TerminalValueRobustnessFixedControlResult(
        completed.scenario,
        completed.schedule_input,
        completed.economic_input,
        completed.schedule_result,
        completed.economic_result,
        completed.schedule_metrics,
        completed.economic_metrics,
        schedule_zero,
        economic_zero,
        break_even,
        delta_cost,
        delta_soc,
        delta_energy,
    )


def _scenario_prices(
    break_even: TerminalValuationBreakEvenEvidence,
) -> tuple[float, ...]:
    values = list(_REQUIRED_VALUATION_PRICES)
    price = break_even.break_even_terminal_valuation_price
    if price is not None and price >= 0.0:
        values.extend((price, price + _BREAK_EVEN_SAMPLE_OFFSET))
        if price > _BREAK_EVEN_SAMPLE_OFFSET:
            values.append(price - _BREAK_EVEN_SAMPLE_OFFSET)
    ordered = sorted(values)
    unique: list[float] = []
    for value in ordered:
        if not unique or abs(value - unique[-1]) > _FLOAT_TOLERANCE:
            unique.append(value)
    return tuple(unique)


def _evaluate_point(
    fixed: TerminalValueRobustnessFixedControlResult,
    price: float,
    terminal_calculator: TerminalEnergyValueBoundary,
    outcome_calculator: EconomicOutcomeBoundary,
) -> TerminalValueRobustnessPoint:
    schedule = _terminal_and_outcome(
        fixed.schedule_metrics,
        fixed.schedule_input.daily_mpc_input.battery_optimization_model,
        price,
        terminal_calculator,
        outcome_calculator,
    )
    economic = _terminal_and_outcome(
        fixed.economic_metrics,
        fixed.economic_input.daily_mpc_input.battery_optimization_model,
        price,
        terminal_calculator,
        outcome_calculator,
    )
    return _point_from_evidence(fixed, price, schedule, economic)


def _point_from_evidence(
    fixed: TerminalValueRobustnessFixedControlResult,
    price: float,
    schedule: tuple[TerminalEnergyValueEvidence, EconomicOutcomeEvidence],
    economic: tuple[TerminalEnergyValueEvidence, EconomicOutcomeEvidence],
) -> TerminalValueRobustnessPoint:
    terminal_delta = (
        economic[0].terminal_energy_value - schedule[0].terminal_energy_value
    )
    net_delta = economic[1].net_economic_cost - schedule[1].net_economic_cost
    return TerminalValueRobustnessPoint(
        fixed,
        fixed.scenario.scenario_id,
        price,
        schedule[0],
        schedule[1],
        economic[0],
        economic[1],
        terminal_delta,
        net_delta,
        _ranking(net_delta),
    )


def _ranking(delta_net_economic_cost: float) -> TerminalValuationRanking:
    if delta_net_economic_cost < -_FLOAT_TOLERANCE:
        return TerminalValuationRanking.ECONOMIC_BETTER
    if delta_net_economic_cost > _FLOAT_TOLERANCE:
        return TerminalValuationRanking.SCHEDULE_BETTER
    return TerminalValuationRanking.BREAK_EVEN


def _scenario_summary_csv(result: TerminalValueRobustnessMatrixResult) -> str:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        (
            "scenario_id",
            "description",
            "schedule_realized_import_cost",
            "economic_realized_import_cost",
            "delta_realized_import_cost",
            "schedule_final_soc",
            "economic_final_soc",
            "delta_final_soc",
            "schedule_deliverable_terminal_energy_kwh",
            "economic_deliverable_terminal_energy_kwh",
            "delta_deliverable_terminal_energy_kwh",
            "analytical_break_even_valuation_price",
            "realized_cost_difference_per_extra_deliverable_kwh",
        )
    )
    for fixed in result.fixed_control_results:
        writer.writerow(
            (
                fixed.scenario.scenario_id,
                fixed.scenario.description,
                _number(fixed.schedule_metrics.grid_import_cost),
                _number(fixed.economic_metrics.grid_import_cost),
                _number(fixed.delta_realized_import_cost),
                _number(fixed.schedule_metrics.final_soc),
                _number(fixed.economic_metrics.final_soc),
                _number(fixed.delta_final_soc),
                _number(
                    fixed.schedule_zero_terminal_evidence.deliverable_terminal_energy_kwh
                ),
                _number(
                    fixed.economic_zero_terminal_evidence.deliverable_terminal_energy_kwh
                ),
                _number(fixed.delta_deliverable_terminal_energy_kwh),
                _optional_number(
                    fixed.break_even_evidence.break_even_terminal_valuation_price
                ),
                _optional_number(
                    fixed.realized_cost_difference_per_extra_deliverable_kwh
                ),
            )
        )
    return stream.getvalue()


def _matrix_csv(result: TerminalValueRobustnessMatrixResult) -> str:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        (
            "scenario_id",
            "valuation_import_price",
            "schedule_terminal_energy_value",
            "economic_terminal_energy_value",
            "delta_terminal_energy_value",
            "schedule_net_economic_cost",
            "economic_net_economic_cost",
            "delta_net_economic_cost",
            "ranking",
        )
    )
    writer.writerows(
        (
            point.scenario_id,
            _number(point.valuation_import_price),
            _number(
                point.schedule_terminal_energy_value_evidence.terminal_energy_value
            ),
            _number(
                point.economic_terminal_energy_value_evidence.terminal_energy_value
            ),
            _number(point.delta_terminal_energy_value),
            _number(point.schedule_economic_outcome_evidence.net_economic_cost),
            _number(point.economic_economic_outcome_evidence.net_economic_cost),
            _number(point.delta_net_economic_cost),
            point.ranking.value,
        )
        for point in result.sensitivity_points
    )
    return stream.getvalue()


def _evaluation_summary(result: TerminalValueRobustnessMatrixResult) -> str:
    blocks = [
        "EOS Terminal Value Robustness Matrix\n",
        "scope: each scenario runs its existing Schedule-aware and Economic Schedule-aware controls once. All valuation points reuse fixed actual trajectories and only calculate TASK-162 terminal evidence plus TASK-163 outcome evidence.\n",
        "ranking_semantics: delta_net_economic_cost = Economic minus Schedule; negative means Economic better, positive means Schedule better, and tolerance-near zero means break-even.\n\n",
    ]
    for fixed in result.fixed_control_results:
        points = result.points_for(fixed.scenario.scenario_id)
        below, above = _nearest_points(points, fixed.break_even_evidence)
        blocks.append(
            f"{fixed.scenario.scenario_id}: {fixed.scenario.description}\n"
            f"actual_terminal_soc: schedule={_number(fixed.schedule_metrics.final_soc)} economic={_number(fixed.economic_metrics.final_soc)} delta_economic_minus_schedule={_number(fixed.delta_final_soc)}\n"
            f"realized_import_cost: schedule={_number(fixed.schedule_metrics.grid_import_cost)} economic={_number(fixed.economic_metrics.grid_import_cost)} delta_economic_minus_schedule={_number(fixed.delta_realized_import_cost)}\n"
            f"deliverable_terminal_energy_kwh: schedule={_number(fixed.schedule_zero_terminal_evidence.deliverable_terminal_energy_kwh)} economic={_number(fixed.economic_zero_terminal_evidence.deliverable_terminal_energy_kwh)} delta_economic_minus_schedule={_number(fixed.delta_deliverable_terminal_energy_kwh)}\n"
            f"analytical_break_even_valuation_price={_optional_number(fixed.break_even_evidence.break_even_terminal_valuation_price)}\n"
            f"below_break_even={_point_summary(below)}\n"
            f"above_break_even={_point_summary(above)}\n"
            f"decomposition: break_even = delta_realized_import_cost / delta_deliverable_terminal_energy; realized_cost_difference_per_extra_deliverable_kwh={_optional_number(fixed.realized_cost_difference_per_extra_deliverable_kwh)}\n\n"
        )
    break_even_values = tuple(
        fixed.break_even_evidence.break_even_terminal_valuation_price
        for fixed in result.fixed_control_results
    )
    blocks.append(
        "cross_scenario_conclusion:\n"
        f"break_even_values={','.join(_optional_number(value) for value in break_even_values)}\n"
        "Break-even is scenario-dependent in this matrix. It depends on both the realized-cost difference and the deliverable-terminal-energy difference; larger terminal SOC divergence alone does not predict a higher or lower threshold. Discharge efficiency is already represented inside TASK-162 deliverable-energy evidence and is not applied again.\n"
        "Terminal valuation is robustly decision-relevant for limited accounting because every scenario crosses an accounting ranking threshold. The evidence is not sufficient for control integration: it excludes export revenue, degradation, uncertainty, and a control objective.\n"
        "These break-even prices are accounting thresholds under TASK-163, not optimized terminal-value coefficients.\n"
    )
    return "".join(blocks)


def _nearest_points(
    points: tuple[TerminalValueRobustnessPoint, ...],
    evidence: TerminalValuationBreakEvenEvidence,
) -> tuple[TerminalValueRobustnessPoint | None, TerminalValueRobustnessPoint | None]:
    price = evidence.break_even_terminal_valuation_price
    if price is None:
        return (None, None)
    below = tuple(point for point in points if point.valuation_import_price < price)
    above = tuple(point for point in points if point.valuation_import_price > price)
    return (None if not below else below[-1], None if not above else above[0])


def _point_summary(point: TerminalValueRobustnessPoint | None) -> str:
    if point is None:
        return "none"
    return (
        f"price={_number(point.valuation_import_price)} "
        f"delta_net_economic_cost={_number(point.delta_net_economic_cost)} "
        f"ranking={point.ranking.value}"
    )


def _break_even_svg(result: TerminalValueRobustnessMatrixResult) -> str:
    values = tuple(
        fixed.break_even_evidence.break_even_terminal_valuation_price or 0.0
        for fixed in result.fixed_control_results
    )
    return _bar_svg(
        "Analytical break-even terminal valuation price by scenario",
        tuple(fixed.scenario.scenario_id for fixed in result.fixed_control_results),
        values,
        "break-even valuation price",
    )


def _soc_delta_svg(result: TerminalValueRobustnessMatrixResult) -> str:
    return _bar_svg(
        "Actual terminal SOC delta by scenario (Economic minus Schedule)",
        tuple(fixed.scenario.scenario_id for fixed in result.fixed_control_results),
        tuple(fixed.delta_final_soc for fixed in result.fixed_control_results),
        "Economic minus Schedule terminal SOC",
    )


def _bar_svg(
    title: str, labels: tuple[str, ...], values: tuple[float, ...], legend: str
) -> str:
    minimum = min(0.0, *values)
    maximum = max(1.0, *values)
    scale = max(maximum - minimum, 1.0)
    baseline = 255.0 - (0.0 - minimum) / scale * 190.0
    bars = "".join(
        f'<rect x="{120 + index * 230}" y="{min(baseline, 255.0 - (value - minimum) / scale * 190.0):.2f}" width="70" height="{abs(baseline - (255.0 - (value - minimum) / scale * 190.0)):.2f}" fill="#2563eb"/>'
        for index, value in enumerate(values)
    )
    label_text = "".join(
        f'<text x="{112 + index * 230}" y="285" font-size="12">{label}</text>'
        for index, label in enumerate(labels)
    )
    return _svg(title, bars, label_text + f'<text x="70" y="330">{legend}</text>')


def _cost_energy_svg(result: TerminalValueRobustnessMatrixResult) -> str:
    values_x = tuple(
        fixed.delta_realized_import_cost for fixed in result.fixed_control_results
    )
    values_y = tuple(
        fixed.delta_deliverable_terminal_energy_kwh
        for fixed in result.fixed_control_results
    )
    minimum_x, maximum_x = min(values_x), max(values_x)
    minimum_y, maximum_y = min(values_y), max(values_y)
    scale_x = max(maximum_x - minimum_x, 1.0)
    scale_y = max(maximum_y - minimum_y, 1.0)
    circles = "".join(
        f'<circle cx="{100 + (x - minimum_x) / scale_x * 820:.2f}" cy="{250 - (y - minimum_y) / scale_y * 180:.2f}" r="8" fill="#7c3aed"/><text x="{110 + (x - minimum_x) / scale_x * 820:.2f}" y="{246 - (y - minimum_y) / scale_y * 180:.2f}" font-size="12">{fixed.scenario.scenario_id}</text>'
        for fixed, x, y in zip(
            result.fixed_control_results, values_x, values_y, strict=True
        )
    )
    return _svg(
        "Realized-cost delta vs deliverable-terminal-energy delta",
        circles,
        '<text x="70" y="330">x: Economic minus Schedule realized cost; y: Economic minus Schedule deliverable terminal energy</text>',
    )


def _heatmap_svg(result: TerminalValueRobustnessMatrixResult) -> str:
    cell_width = 60
    cell_height = 38
    cells: list[str] = []
    labels: list[str] = []
    for row, fixed in enumerate(result.fixed_control_results):
        points = result.points_for(fixed.scenario.scenario_id)
        labels.append(
            f'<text x="8" y="{85 + row * cell_height}" font-size="11">{fixed.scenario.scenario_id}</text>'
        )
        for column, point in enumerate(points):
            fill = {
                TerminalValuationRanking.ECONOMIC_BETTER: "#059669",
                TerminalValuationRanking.SCHEDULE_BETTER: "#dc2626",
                TerminalValuationRanking.BREAK_EVEN: "#64748b",
            }[point.ranking]
            cells.append(
                f'<rect x="{140 + column * cell_width}" y="{55 + row * cell_height}" width="{cell_width - 2}" height="{cell_height - 2}" fill="{fill}"/>'
            )
            if row == 0:
                labels.append(
                    f'<text x="{141 + column * cell_width}" y="45" font-size="9">{point.valuation_import_price:.3f}</text>'
                )
    return _svg(
        "Net economic cost delta ranking heatmap",
        "".join(cells),
        "".join(labels)
        + '<text x="70" y="330" fill="#059669">Economic better</text><text x="240" y="330" fill="#dc2626">Schedule better</text><text x="420" y="330" fill="#64748b">Break-even</text>',
    )


def _svg(title: str, content: str, footer: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="360" viewBox="0 0 1024 360">'
        '<rect width="100%" height="100%" fill="white"/>'
        f'<text x="70" y="28" font-family="sans-serif" font-size="16">{title}</text>'
        '<line x1="70" y1="255" x2="980" y2="255" stroke="#64748b"/>'
        f"{content}{footer}</svg>\n"
    )


def _non_negative(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if normalized < 0.0:
        raise ValueError(f"{field_name} must be non-negative")
    return normalized


def _number(value: float) -> str:
    return f"{value:.6f}"


def _optional_number(value: float | None) -> str:
    return "" if value is None else _number(value)


if __name__ == "__main__":
    raise SystemExit(main())
