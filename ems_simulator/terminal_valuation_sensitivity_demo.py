# ruff: noqa: E501
"""Observe TASK-165 accounting sensitivity to terminal valuation price.

TASK-166 runs the two frozen TASK-165 control paths exactly once, then performs
only TASK-162 terminal-value and TASK-163 economic-outcome post-processing for
each explicit valuation price.  It owns no control, planning, MPC, feasibility,
actuation, or Simulator algorithm and does not change actual trajectories.
"""

import argparse
import csv
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from io import StringIO
from itertools import pairwise
from math import isfinite
from pathlib import Path

from ems_simulator.terminal_soc_divergence_economic_demo import (
    TerminalSOCDivergencePathResult,
    TerminalSOCDivergenceResult,
    run_terminal_soc_divergence_evaluation,
)
from optimization import (
    DeterministicEconomicOutcomeCalculator,
    DeterministicTerminalEnergyValueCalculator,
    EconomicOutcomeBoundary,
    EconomicOutcomeEvidence,
    EconomicOutcomeInput,
    TerminalEnergyValueBoundary,
    TerminalEnergyValueEvidence,
    TerminalEnergyValueInput,
)

_FLOAT_TOLERANCE = 1e-9
_DEFAULT_VALUATION_PRICES = (
    0.00,
    0.40,
    0.60,
    0.75,
    0.80,
    0.85,
    0.88,
    0.886,
    0.8864,
    0.886426,
    0.89,
    0.90,
    1.00,
    1.20,
)


class TerminalValuationRanking(StrEnum):
    """Rank the fixed paths by Economic minus Schedule net accounting cost."""

    SCHEDULE_BETTER = "schedule_better"
    ECONOMIC_BETTER = "economic_better"
    BREAK_EVEN = "break_even"


@dataclass(frozen=True, slots=True)
class TerminalValuationBreakEvenEvidence:
    """Analytical threshold derived from two already-observed fixed paths."""

    delta_realized_import_cost: float
    delta_deliverable_terminal_energy_kwh: float
    break_even_terminal_valuation_price: float | None
    available: bool

    def __post_init__(self) -> None:
        delta_cost = _finite(
            self.delta_realized_import_cost, "delta_realized_import_cost"
        )
        delta_energy = _finite(
            self.delta_deliverable_terminal_energy_kwh,
            "delta_deliverable_terminal_energy_kwh",
        )
        if not isinstance(self.available, bool):
            raise TypeError("available must be a bool")
        expected_available = abs(delta_energy) > _FLOAT_TOLERANCE
        if self.available != expected_available:
            raise ValueError("available must reflect deliverable-energy denominator")
        price = self.break_even_terminal_valuation_price
        if not self.available:
            if price is not None:
                raise ValueError("unavailable break-even must have no price")
        else:
            if price is None:
                raise ValueError("available break-even must provide a price")
            normalized_price = _finite(price, "break_even_terminal_valuation_price")
            expected_price = delta_cost / delta_energy
            if normalized_price != expected_price:
                raise ValueError(
                    "break-even price must use the frozen analytical formula"
                )
            object.__setattr__(
                self, "break_even_terminal_valuation_price", normalized_price
            )
        object.__setattr__(self, "delta_realized_import_cost", delta_cost)
        object.__setattr__(
            self,
            "delta_deliverable_terminal_energy_kwh",
            delta_energy,
        )


@dataclass(frozen=True, slots=True)
class TerminalValuationSensitivityPoint:
    """TASK-162/163 accounting evidence for both fixed paths at one price."""

    valuation_import_price: float
    schedule_terminal_energy_value_evidence: TerminalEnergyValueEvidence
    schedule_economic_outcome_evidence: EconomicOutcomeEvidence
    economic_terminal_energy_value_evidence: TerminalEnergyValueEvidence
    economic_economic_outcome_evidence: EconomicOutcomeEvidence
    delta_terminal_energy_value: float
    delta_net_economic_cost: float
    ranking: TerminalValuationRanking

    def __post_init__(self) -> None:
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
            raise TypeError(
                "terminal value evidence must be TerminalEnergyValueEvidence"
            )
        if not all(isinstance(item, EconomicOutcomeEvidence) for item in outcomes):
            raise TypeError("economic outcome evidence must be EconomicOutcomeEvidence")
        for item in evidence:
            if item.source_input.valuation_import_price != price:
                raise ValueError(
                    "terminal evidence must preserve the point valuation price"
                )
        if (
            self.schedule_economic_outcome_evidence.terminal_energy_value_evidence
            is not self.schedule_terminal_energy_value_evidence
        ):
            raise ValueError("schedule outcome must preserve exact terminal evidence")
        if (
            self.economic_economic_outcome_evidence.terminal_energy_value_evidence
            is not self.economic_terminal_energy_value_evidence
        ):
            raise ValueError("economic outcome must preserve exact terminal evidence")
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
        object.__setattr__(
            self,
            "delta_terminal_energy_value",
            _finite(self.delta_terminal_energy_value, "delta_terminal_energy_value"),
        )
        object.__setattr__(
            self,
            "delta_net_economic_cost",
            _finite(self.delta_net_economic_cost, "delta_net_economic_cost"),
        )


@dataclass(frozen=True, slots=True)
class TerminalValuationSensitivityResult:
    """Fixed TASK-165 paths plus ordered terminal-price accounting evidence."""

    source_task_165_result: TerminalSOCDivergenceResult
    break_even_evidence: TerminalValuationBreakEvenEvidence
    sensitivity_points: tuple[TerminalValuationSensitivityPoint, ...]
    sensitivity_csv_path: Path
    break_even_summary_path: Path
    evaluation_summary_path: Path
    net_economic_cost_svg_path: Path
    net_cost_delta_svg_path: Path

    def __post_init__(self) -> None:
        if not isinstance(self.source_task_165_result, TerminalSOCDivergenceResult):
            raise TypeError(
                "source_task_165_result must be a TerminalSOCDivergenceResult"
            )
        if not isinstance(self.break_even_evidence, TerminalValuationBreakEvenEvidence):
            raise TypeError(
                "break_even_evidence must be TerminalValuationBreakEvenEvidence"
            )
        if not isinstance(self.sensitivity_points, tuple):
            raise TypeError("sensitivity_points must be a tuple")
        if not self.sensitivity_points:
            raise ValueError("sensitivity_points must not be empty")
        if not all(
            isinstance(point, TerminalValuationSensitivityPoint)
            for point in self.sensitivity_points
        ):
            raise TypeError(
                "sensitivity_points must contain TerminalValuationSensitivityPoint"
            )
        prices = tuple(
            point.valuation_import_price for point in self.sensitivity_points
        )
        if any(left >= right for left, right in pairwise(prices)):
            raise ValueError("sensitivity point prices must be strictly ordered")
        source = self.source_task_165_result
        if self.break_even_evidence.delta_realized_import_cost != (
            source.economic.economic_outcome_evidence.realized_import_cost
            - source.schedule.economic_outcome_evidence.realized_import_cost
        ):
            raise ValueError(
                "break-even realized-cost delta must retain TASK-165 evidence"
            )
        if self.break_even_evidence.delta_deliverable_terminal_energy_kwh != (
            source.economic.terminal_energy_value_evidence.deliverable_terminal_energy_kwh
            - source.schedule.terminal_energy_value_evidence.deliverable_terminal_energy_kwh
        ):
            raise ValueError("break-even energy delta must retain TASK-165 evidence")
        if not all(isinstance(path, Path) for path in self.output_paths):
            raise TypeError("output paths must be pathlib.Path instances")

    @property
    def output_paths(self) -> tuple[Path, ...]:
        """Return emitted TASK-166 artifacts in stable caller-facing order."""

        return (
            self.sensitivity_csv_path,
            self.break_even_summary_path,
            self.evaluation_summary_path,
            self.net_economic_cost_svg_path,
            self.net_cost_delta_svg_path,
        )


def run_terminal_valuation_sensitivity(
    output_directory: Path,
    valuation_prices: tuple[float, ...] = _DEFAULT_VALUATION_PRICES,
    terminal_value_calculator: TerminalEnergyValueBoundary | None = None,
    outcome_calculator: EconomicOutcomeBoundary | None = None,
) -> TerminalValuationSensitivityResult:
    """Run fixed TASK-165 controls once, then vary terminal accounting only."""

    if not isinstance(output_directory, Path):
        raise TypeError("output_directory must be a pathlib.Path")
    prices = _valuation_prices(valuation_prices)
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
    fixed_result = run_terminal_soc_divergence_evaluation(
        output_directory / "task_165_fixed_control"
    )
    break_even = _break_even_evidence(fixed_result)
    all_prices = _with_break_even_price(prices, break_even)
    points = tuple(
        _evaluate_point(
            price,
            fixed_result.schedule,
            fixed_result.economic,
            terminal_calculator,
            net_cost_calculator,
        )
        for price in all_prices
    )
    sensitivity_csv_path = output_directory / "terminal_valuation_sensitivity.csv"
    break_even_summary_path = output_directory / "break_even_summary.txt"
    evaluation_summary_path = output_directory / "evaluation_summary.txt"
    net_economic_cost_svg_path = (
        output_directory / "net_economic_cost_vs_terminal_price.svg"
    )
    net_cost_delta_svg_path = output_directory / "net_cost_delta_vs_terminal_price.svg"
    sensitivity_csv_path.write_text(
        _sensitivity_csv(points), encoding="utf-8", newline=""
    )
    break_even_summary_path.write_text(
        _break_even_summary(fixed_result, break_even, points),
        encoding="utf-8",
        newline="",
    )
    evaluation_summary_path.write_text(
        _evaluation_summary(fixed_result, break_even, points),
        encoding="utf-8",
        newline="",
    )
    net_economic_cost_svg_path.write_text(_net_cost_svg(points), encoding="utf-8")
    net_cost_delta_svg_path.write_text(_delta_svg(points), encoding="utf-8")
    return TerminalValuationSensitivityResult(
        fixed_result,
        break_even,
        points,
        sensitivity_csv_path,
        break_even_summary_path,
        evaluation_summary_path,
        net_economic_cost_svg_path,
        net_cost_delta_svg_path,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the deterministic TASK-166 terminal valuation sensitivity CLI."""

    parser = argparse.ArgumentParser(
        description="EOS TASK-166 terminal valuation price sensitivity evaluation"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("simulation_output_task166_terminal_valuation_sensitivity"),
    )
    arguments = parser.parse_args(argv)
    result = run_terminal_valuation_sensitivity(arguments.output_dir)
    for path in result.output_paths:
        print(path)
    return 0


def _valuation_prices(values: tuple[float, ...]) -> tuple[float, ...]:
    if not isinstance(values, tuple):
        raise TypeError("valuation_prices must be a tuple")
    if not values:
        raise ValueError("valuation_prices must not be empty")
    prices = tuple(_non_negative(value, "valuation_prices item") for value in values)
    if any(left >= right for left, right in pairwise(prices)):
        raise ValueError("valuation_prices must be strictly increasing")
    return prices


def _break_even_evidence(
    source: TerminalSOCDivergenceResult,
) -> TerminalValuationBreakEvenEvidence:
    delta_cost = (
        source.economic.economic_outcome_evidence.realized_import_cost
        - source.schedule.economic_outcome_evidence.realized_import_cost
    )
    delta_energy = (
        source.economic.terminal_energy_value_evidence.deliverable_terminal_energy_kwh
        - source.schedule.terminal_energy_value_evidence.deliverable_terminal_energy_kwh
    )
    available = abs(delta_energy) > _FLOAT_TOLERANCE
    return TerminalValuationBreakEvenEvidence(
        delta_cost,
        delta_energy,
        None if not available else delta_cost / delta_energy,
        available,
    )


def _with_break_even_price(
    prices: tuple[float, ...],
    break_even: TerminalValuationBreakEvenEvidence,
) -> tuple[float, ...]:
    """Add the exact non-negative threshold to make classification observable."""

    price = break_even.break_even_terminal_valuation_price
    if price is None or price < 0.0:
        return prices
    if any(abs(existing - price) <= _FLOAT_TOLERANCE for existing in prices):
        return prices
    return tuple(sorted((*prices, price)))


def _evaluate_point(
    price: float,
    schedule: TerminalSOCDivergencePathResult,
    economic: TerminalSOCDivergencePathResult,
    terminal_calculator: TerminalEnergyValueBoundary,
    outcome_calculator: EconomicOutcomeBoundary,
) -> TerminalValuationSensitivityPoint:
    schedule_terminal = terminal_calculator.calculate(
        TerminalEnergyValueInput(
            schedule.source_metrics.final_soc,
            schedule.terminal_energy_value_evidence.source_input.battery_model,
            price,
        )
    )
    schedule_outcome = outcome_calculator.calculate(
        EconomicOutcomeInput(
            schedule.source_metrics.grid_import_cost,
            schedule_terminal,
        )
    )
    economic_terminal = terminal_calculator.calculate(
        TerminalEnergyValueInput(
            economic.source_metrics.final_soc,
            economic.terminal_energy_value_evidence.source_input.battery_model,
            price,
        )
    )
    economic_outcome = outcome_calculator.calculate(
        EconomicOutcomeInput(
            economic.source_metrics.grid_import_cost,
            economic_terminal,
        )
    )
    terminal_delta = (
        economic_terminal.terminal_energy_value
        - schedule_terminal.terminal_energy_value
    )
    net_delta = economic_outcome.net_economic_cost - schedule_outcome.net_economic_cost
    return TerminalValuationSensitivityPoint(
        price,
        schedule_terminal,
        schedule_outcome,
        economic_terminal,
        economic_outcome,
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


def _sensitivity_csv(points: tuple[TerminalValuationSensitivityPoint, ...]) -> str:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        (
            "valuation_import_price",
            "schedule_terminal_value",
            "economic_terminal_value",
            "delta_terminal_value",
            "schedule_net_economic_cost",
            "economic_net_economic_cost",
            "delta_net_economic_cost",
            "ranking",
            "schedule_realized_import_cost",
            "economic_realized_import_cost",
            "schedule_deliverable_terminal_energy_kwh",
            "economic_deliverable_terminal_energy_kwh",
        )
    )
    writer.writerows(
        (
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
            _number(point.schedule_economic_outcome_evidence.realized_import_cost),
            _number(point.economic_economic_outcome_evidence.realized_import_cost),
            _number(
                point.schedule_terminal_energy_value_evidence.deliverable_terminal_energy_kwh
            ),
            _number(
                point.economic_terminal_energy_value_evidence.deliverable_terminal_energy_kwh
            ),
        )
        for point in points
    )
    return stream.getvalue()


def _break_even_summary(
    fixed: TerminalSOCDivergenceResult,
    break_even: TerminalValuationBreakEvenEvidence,
    points: tuple[TerminalValuationSensitivityPoint, ...],
) -> str:
    schedule = fixed.schedule
    economic = fixed.economic
    below, above = _nearest_points(points, break_even)
    price = break_even.break_even_terminal_valuation_price
    return (
        "EOS Terminal Valuation Price Sensitivity — Break-even Summary\n"
        f"schedule_realized_import_cost={_number(schedule.economic_outcome_evidence.realized_import_cost)}\n"
        f"economic_realized_import_cost={_number(economic.economic_outcome_evidence.realized_import_cost)}\n"
        f"delta_realized_import_cost_economic_minus_schedule={_number(break_even.delta_realized_import_cost)}\n"
        f"schedule_deliverable_terminal_energy_kwh={_number(schedule.terminal_energy_value_evidence.deliverable_terminal_energy_kwh)}\n"
        f"economic_deliverable_terminal_energy_kwh={_number(economic.terminal_energy_value_evidence.deliverable_terminal_energy_kwh)}\n"
        f"delta_deliverable_terminal_energy_kwh_economic_minus_schedule={_number(break_even.delta_deliverable_terminal_energy_kwh)}\n"
        f"analytical_break_even_terminal_valuation_price={_optional_number(price)} available={str(break_even.available).lower()}\n"
        f"nearest_sample_below={_point_summary(below)}\n"
        f"nearest_sample_above={_point_summary(above)}\n"
        "The break-even price is an accounting threshold under the limited TASK-163 model, not an optimized battery shadow price.\n"
    )


def _evaluation_summary(
    fixed: TerminalSOCDivergenceResult,
    break_even: TerminalValuationBreakEvenEvidence,
    points: tuple[TerminalValuationSensitivityPoint, ...],
) -> str:
    price = break_even.break_even_terminal_valuation_price
    below, above = _nearest_points(points, break_even)
    price_085 = _point_at(points, 0.85)
    price_090 = _point_at(points, 0.90)
    transition = "not available" if price is None else _number(price)
    return (
        "EOS Terminal Valuation Price Sensitivity Evaluation\n"
        "fixed_control_behavior: TASK-165 Schedule-aware and Economic Schedule-aware daily simulations execute once. Their battery actions, actual SOC trajectories, grid energy, realized import cost, PV absorption, and throughput are fixed before valuation sensitivity.\n"
        f"fixed_schedule: realized_import_cost={_number(fixed.schedule.source_metrics.grid_import_cost)} final_soc={_number(fixed.schedule.source_metrics.final_soc)} grid_import_kwh={_number(fixed.schedule.source_metrics.grid_import_energy_kwh)} throughput_kwh={_number(fixed.schedule.source_metrics.battery_throughput_kwh)}\n"
        f"fixed_economic: realized_import_cost={_number(fixed.economic.source_metrics.grid_import_cost)} final_soc={_number(fixed.economic.source_metrics.final_soc)} grid_import_kwh={_number(fixed.economic.source_metrics.grid_import_energy_kwh)} throughput_kwh={_number(fixed.economic.source_metrics.battery_throughput_kwh)}\n"
        "valuation_scope: each point only recalculates TASK-162 TerminalEnergyValueEvidence and TASK-163 EconomicOutcomeEvidence; it never reruns MPC, optimization, feasibility, handoff, or Simulator execution.\n"
        f"analytical_break_even_terminal_valuation_price={transition}\n"
        f"at_0.85={_point_summary(price_085)}\n"
        f"at_0.90={_point_summary(price_090)}\n"
        f"below_break_even={_point_summary(below)}\n"
        f"above_break_even={_point_summary(above)}\n"
        "ranking_semantics: delta_net_economic_cost = Economic minus Schedule; negative means Economic better, positive means Schedule better, and tolerance-near zero means break-even.\n"
        "interpretation: the sampled ranking reverses across the analytical threshold. Terminal value is clearly decision-relevant for accounting in this fixture, but sensitivity evidence alone does not justify adding terminal value to control; retain it as observational evidence pending valuation-price and broader scenario studies.\n"
        "sensitivity_table:\n"
        + "".join(
            f"price={_number(point.valuation_import_price)} schedule_net={_number(point.schedule_economic_outcome_evidence.net_economic_cost)} economic_net={_number(point.economic_economic_outcome_evidence.net_economic_cost)} delta={_number(point.delta_net_economic_cost)} ranking={point.ranking.value}\n"
            for point in points
        )
    )


def _nearest_points(
    points: tuple[TerminalValuationSensitivityPoint, ...],
    evidence: TerminalValuationBreakEvenEvidence,
) -> tuple[
    TerminalValuationSensitivityPoint | None, TerminalValuationSensitivityPoint | None
]:
    price = evidence.break_even_terminal_valuation_price
    if price is None:
        return (None, None)
    below = tuple(point for point in points if point.valuation_import_price < price)
    above = tuple(point for point in points if point.valuation_import_price > price)
    return (
        None if not below else below[-1],
        None if not above else above[0],
    )


def _point_at(
    points: tuple[TerminalValuationSensitivityPoint, ...], price: float
) -> TerminalValuationSensitivityPoint | None:
    return next(
        (point for point in points if point.valuation_import_price == price),
        None,
    )


def _point_summary(point: TerminalValuationSensitivityPoint | None) -> str:
    if point is None:
        return "none"
    return (
        f"price={_number(point.valuation_import_price)} "
        f"delta_net_economic_cost={_number(point.delta_net_economic_cost)} "
        f"ranking={point.ranking.value}"
    )


def _net_cost_svg(points: tuple[TerminalValuationSensitivityPoint, ...]) -> str:
    return _line_svg(
        "Net economic cost vs terminal valuation price",
        points,
        tuple(
            point.schedule_economic_outcome_evidence.net_economic_cost
            for point in points
        ),
        tuple(
            point.economic_economic_outcome_evidence.net_economic_cost
            for point in points
        ),
        "Schedule",
        "Economic",
        False,
    )


def _delta_svg(points: tuple[TerminalValuationSensitivityPoint, ...]) -> str:
    values = tuple(point.delta_net_economic_cost for point in points)
    return _line_svg(
        "Net-cost delta vs terminal valuation price (Economic minus Schedule)",
        points,
        values,
        (),
        "Economic minus Schedule",
        "",
        True,
    )


def _line_svg(
    title: str,
    points: tuple[TerminalValuationSensitivityPoint, ...],
    first: tuple[float, ...],
    second: tuple[float, ...],
    first_label: str,
    second_label: str,
    zero_reference: bool,
) -> str:
    x_values = tuple(point.valuation_import_price for point in points)
    zero_values = (0.0,) if zero_reference else ()
    values = (*first, *second, *zero_values)
    minimum = float(min(values))
    maximum = float(max(values))
    scale_y = max(maximum - minimum, 1.0)
    scale_x = max(x_values[-1] - x_values[0], 1.0)

    def x(value: float) -> float:
        return 70.0 + (value - x_values[0]) / scale_x * 890.0

    def y(value: float) -> float:
        return 255.0 - (value - minimum) / scale_y * 190.0

    def svg_points(values_: tuple[float, ...]) -> str:
        return " ".join(
            f"{x(price):.2f},{y(value):.2f}"
            for price, value in zip(x_values, values_, strict=True)
        )

    series = f'<polyline fill="none" stroke="#2563eb" stroke-width="2" points="{svg_points(first)}"/>'
    if second:
        series += f'<polyline fill="none" stroke="#059669" stroke-width="2" points="{svg_points(second)}"/>'
    zero = ""
    if zero_reference:
        zero = f'<line x1="70" y1="{y(0.0):.2f}" x2="960" y2="{y(0.0):.2f}" stroke="#dc2626" stroke-dasharray="5 4"/>'
    legend = f'<text x="70" y="330" fill="#2563eb">{first_label}</text>'
    if second_label:
        legend += f'<text x="250" y="330" fill="#059669">{second_label}</text>'
    if zero_reference:
        legend += '<text x="540" y="330" fill="#dc2626">zero reference</text>'
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="360" viewBox="0 0 1024 360">'
        '<rect width="100%" height="100%" fill="white"/>'
        f'<text x="70" y="28" font-family="sans-serif" font-size="16">{title}</text>'
        '<line x1="70" y1="255" x2="960" y2="255" stroke="#64748b"/>'
        f"{zero}{series}{legend}</svg>\n"
    )


def _finite(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    return normalized


def _non_negative(value: object, field_name: str) -> float:
    normalized = _finite(value, field_name)
    if normalized < 0.0:
        raise ValueError(f"{field_name} must be non-negative")
    return normalized


def _number(value: float) -> str:
    return f"{value:.6f}"


def _optional_number(value: float | None) -> str:
    return "" if value is None else _number(value)


if __name__ == "__main__":
    raise SystemExit(main())
