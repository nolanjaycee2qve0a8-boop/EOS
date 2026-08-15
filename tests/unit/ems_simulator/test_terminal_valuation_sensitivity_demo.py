"""Focused observational tests for TASK-166 terminal valuation sensitivity."""

from pathlib import Path

import pytest

from ems_simulator.terminal_soc_divergence_economic_demo import (
    TerminalSOCDivergenceResult,
    run_terminal_soc_divergence_evaluation,
)
from ems_simulator.terminal_valuation_sensitivity_demo import (
    TerminalValuationBreakEvenEvidence,
    TerminalValuationRanking,
    run_terminal_valuation_sensitivity,
)
from optimization import (
    DeterministicEconomicOutcomeCalculator,
    DeterministicTerminalEnergyValueCalculator,
    EconomicOutcomeEvidence,
    EconomicOutcomeInput,
    TerminalEnergyValueEvidence,
    TerminalEnergyValueInput,
)


class CountingTerminalValueCalculator(DeterministicTerminalEnergyValueCalculator):
    """Count point-level TASK-162 calls without changing its formula."""

    __slots__ = ("calls",)

    def __init__(self) -> None:
        self.calls: list[TerminalEnergyValueInput] = []

    def calculate(
        self,
        value_input: TerminalEnergyValueInput,
    ) -> TerminalEnergyValueEvidence:
        self.calls.append(value_input)
        return super().calculate(value_input)


class CountingOutcomeCalculator(DeterministicEconomicOutcomeCalculator):
    """Count point-level TASK-163 calls without changing its formula."""

    __slots__ = ("calls",)

    def __init__(self) -> None:
        self.calls: list[EconomicOutcomeInput] = []

    def calculate(self, outcome_input: EconomicOutcomeInput) -> EconomicOutcomeEvidence:
        self.calls.append(outcome_input)
        return super().calculate(outcome_input)


def test_sensitivity_preserves_fixed_task_165_actual_behavior(tmp_path: Path) -> None:
    result = run_terminal_valuation_sensitivity(tmp_path)

    schedule = result.source_task_165_result.schedule.source_metrics
    economic = result.source_task_165_result.economic.source_metrics
    assert schedule.grid_import_cost == pytest.approx(22.840526315789482)
    assert economic.grid_import_cost == pytest.approx(18.63)
    assert schedule.final_soc == pytest.approx(1.0)
    assert economic.final_soc == pytest.approx(0.5)
    assert {
        point.schedule_economic_outcome_evidence.realized_import_cost
        for point in result.sensitivity_points
    } == {schedule.grid_import_cost}
    assert {
        point.economic_economic_outcome_evidence.realized_import_cost
        for point in result.sensitivity_points
    } == {economic.grid_import_cost}
    assert {
        point.schedule_terminal_energy_value_evidence.deliverable_terminal_energy_kwh
        for point in result.sensitivity_points
    } == {7.6}
    assert all(
        point.economic_terminal_energy_value_evidence.deliverable_terminal_energy_kwh
        == pytest.approx(2.85)
        for point in result.sensitivity_points
    )


def test_sensitivity_is_linear_and_crosses_analytical_break_even(
    tmp_path: Path,
) -> None:
    result = run_terminal_valuation_sensitivity(tmp_path)
    break_even = result.break_even_evidence
    exact = next(
        point
        for point in result.sensitivity_points
        if point.valuation_import_price
        == break_even.break_even_terminal_valuation_price
    )
    point_085 = next(
        point
        for point in result.sensitivity_points
        if point.valuation_import_price == 0.85
    )
    point_090 = next(
        point
        for point in result.sensitivity_points
        if point.valuation_import_price == 0.90
    )

    assert break_even.available is True
    assert break_even.break_even_terminal_valuation_price == pytest.approx(
        break_even.delta_realized_import_cost
        / break_even.delta_deliverable_terminal_energy_kwh
    )
    assert break_even.break_even_terminal_valuation_price == pytest.approx(0.8864265928)
    assert point_085.ranking is TerminalValuationRanking.ECONOMIC_BETTER
    assert point_090.ranking is TerminalValuationRanking.SCHEDULE_BETTER
    assert exact.ranking is TerminalValuationRanking.BREAK_EVEN
    assert point_085.delta_net_economic_cost == pytest.approx(-0.17302631578948357)
    assert point_090.delta_net_economic_cost == pytest.approx(0.0644736842105145)


def test_task_162_and_163_execute_once_per_path_per_sensitivity_point(
    tmp_path: Path,
) -> None:
    terminal_calculator = CountingTerminalValueCalculator()
    outcome_calculator = CountingOutcomeCalculator()
    result = run_terminal_valuation_sensitivity(
        tmp_path,
        (0.0, 1.0),
        terminal_calculator,
        outcome_calculator,
    )

    assert len(terminal_calculator.calls) == len(result.sensitivity_points) * 2
    assert len(outcome_calculator.calls) == len(result.sensitivity_points) * 2
    assert all(
        point.schedule_economic_outcome_evidence.terminal_energy_value_evidence
        is point.schedule_terminal_energy_value_evidence
        for point in result.sensitivity_points
    )
    assert all(
        point.economic_economic_outcome_evidence.terminal_energy_value_evidence
        is point.economic_terminal_energy_value_evidence
        for point in result.sensitivity_points
    )


def test_fixed_task_165_control_executes_once_not_once_per_price(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = run_terminal_soc_divergence_evaluation
    calls = 0

    def counted_task_165(output_directory: Path) -> TerminalSOCDivergenceResult:
        nonlocal calls
        calls += 1
        return original(output_directory)

    monkeypatch.setattr(
        "ems_simulator.terminal_valuation_sensitivity_demo.run_terminal_soc_divergence_evaluation",
        counted_task_165,
    )

    run_terminal_valuation_sensitivity(tmp_path, (0.0, 0.40, 1.20))

    assert calls == 1


def test_zero_deliverable_energy_delta_exposes_unavailable_break_even() -> None:
    evidence = TerminalValuationBreakEvenEvidence(-1.0, 0.0, None, False)

    assert evidence.available is False
    assert evidence.break_even_terminal_valuation_price is None


def test_outputs_are_byte_deterministic_and_explain_observational_scope(
    tmp_path: Path,
) -> None:
    first = run_terminal_valuation_sensitivity(tmp_path / "first")
    second = run_terminal_valuation_sensitivity(tmp_path / "second")

    assert all(
        left.read_text(encoding="utf-8") == right.read_text(encoding="utf-8")
        for left, right in zip(first.output_paths, second.output_paths, strict=True)
    )
    summary = first.evaluation_summary_path.read_text(encoding="utf-8")
    assert (
        "never reruns MPC, optimization, feasibility, handoff, or Simulator execution"
        in summary
    )
    assert (
        "sensitivity evidence alone does not justify adding terminal value to control"
        in summary
    )
    csv_rows = first.sensitivity_csv_path.read_text(encoding="utf-8").splitlines()
    assert len(csv_rows) == len(first.sensitivity_points) + 1
    assert "ranking" in csv_rows[0]
