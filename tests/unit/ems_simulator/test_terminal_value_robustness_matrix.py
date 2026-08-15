"""Focused TASK-167 terminal-value robustness matrix tests."""

from pathlib import Path

import pytest

from ems_simulator.terminal_valuation_sensitivity_demo import TerminalValuationRanking
from ems_simulator.terminal_value_robustness_matrix import (
    TerminalValueRobustnessScenario,
    _CompletedControlPaths,
    _run_fixed_control,
    run_terminal_value_robustness_matrix,
    scenario_matrix,
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
    """Count point-level TASK-162 calls without changing valuation semantics."""

    __slots__ = ("calls",)

    def __init__(self) -> None:
        self.calls: list[TerminalEnergyValueInput] = []

    def calculate(
        self, value_input: TerminalEnergyValueInput
    ) -> TerminalEnergyValueEvidence:
        self.calls.append(value_input)
        return super().calculate(value_input)


class CountingOutcomeCalculator(DeterministicEconomicOutcomeCalculator):
    """Count point-level TASK-163 calls without changing outcome semantics."""

    __slots__ = ("calls",)

    def __init__(self) -> None:
        self.calls: list[EconomicOutcomeInput] = []

    def calculate(self, outcome_input: EconomicOutcomeInput) -> EconomicOutcomeEvidence:
        self.calls.append(outcome_input)
        return super().calculate(outcome_input)


def test_required_scenarios_are_ordered_and_have_distinct_actual_soc_divergence(
    tmp_path: Path,
) -> None:
    scenarios = scenario_matrix()
    result = run_terminal_value_robustness_matrix(tmp_path)

    assert tuple(item.scenario_id for item in scenarios) == (
        "R1_SMALL",
        "R2_MEDIUM",
        "R3_LARGE_TASK165_BASELINE",
    )
    deltas = tuple(item.delta_final_soc for item in result.fixed_control_results)
    assert all(delta < 0.0 for delta in deltas)
    assert tuple(abs(delta) for delta in deltas) == tuple(
        sorted(abs(delta) for delta in deltas)
    )
    assert len(set(deltas)) == 3
    assert all(
        len(item.schedule_result.step_traces) == 24
        for item in result.fixed_control_results
    )
    assert all(
        len(item.economic_result.step_traces) == 24
        for item in result.fixed_control_results
    )


def test_fixed_control_metrics_do_not_change_across_valuation_points(
    tmp_path: Path,
) -> None:
    result = run_terminal_value_robustness_matrix(tmp_path)

    for fixed in result.fixed_control_results:
        points = result.points_for(fixed.scenario.scenario_id)
        assert all(point.source_fixed_control_result is fixed for point in points)
        assert {
            point.schedule_economic_outcome_evidence.realized_import_cost
            for point in points
        } == {fixed.schedule_metrics.grid_import_cost}
        assert {
            point.economic_economic_outcome_evidence.realized_import_cost
            for point in points
        } == {fixed.economic_metrics.grid_import_cost}
        assert {
            point.schedule_terminal_energy_value_evidence.deliverable_terminal_energy_kwh
            for point in points
        } == {fixed.schedule_zero_terminal_evidence.deliverable_terminal_energy_kwh}
        assert all(
            point.economic_terminal_energy_value_evidence.deliverable_terminal_energy_kwh
            == pytest.approx(
                fixed.economic_zero_terminal_evidence.deliverable_terminal_energy_kwh
            )
            for point in points
        )


def test_each_available_break_even_has_opposite_rankings_on_both_sides(
    tmp_path: Path,
) -> None:
    result = run_terminal_value_robustness_matrix(tmp_path)

    for fixed in result.fixed_control_results:
        evidence = fixed.break_even_evidence
        price = evidence.break_even_terminal_valuation_price
        assert evidence.available is True
        assert price is not None
        assert price == pytest.approx(
            evidence.delta_realized_import_cost
            / evidence.delta_deliverable_terminal_energy_kwh
        )
        points = result.points_for(fixed.scenario.scenario_id)
        exact = next(point for point in points if point.valuation_import_price == price)
        below = max(
            (point for point in points if point.valuation_import_price < price),
            key=lambda point: point.valuation_import_price,
        )
        above = min(
            (point for point in points if point.valuation_import_price > price),
            key=lambda point: point.valuation_import_price,
        )
        assert exact.ranking is TerminalValuationRanking.BREAK_EVEN
        assert below.ranking is TerminalValuationRanking.ECONOMIC_BETTER
        assert above.ranking is TerminalValuationRanking.SCHEDULE_BETTER


def test_task_165_baseline_break_even_reproduces(tmp_path: Path) -> None:
    result = run_terminal_value_robustness_matrix(tmp_path)
    baseline = result.fixed_control_results[-1]

    assert baseline.scenario.scenario_id == "R3_LARGE_TASK165_BASELINE"
    assert baseline.delta_final_soc == pytest.approx(-0.5)
    assert (
        baseline.break_even_evidence.break_even_terminal_valuation_price
        == pytest.approx(0.8864265928)
    )


def test_task_162_and_163_calls_scale_with_points_not_control_reruns(
    tmp_path: Path,
) -> None:
    terminal = CountingTerminalValueCalculator()
    outcome = CountingOutcomeCalculator()
    result = run_terminal_value_robustness_matrix(tmp_path, terminal, outcome)

    assert len(terminal.calls) == len(result.sensitivity_points) * 2
    assert len(outcome.calls) == len(result.sensitivity_points) * 2


def test_each_scenario_control_pair_executes_once_not_once_per_valuation_point(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = _run_fixed_control
    calls = 0

    def counted(
        scenario: TerminalValueRobustnessScenario,
        output_directory: Path,
    ) -> _CompletedControlPaths:
        nonlocal calls
        calls += 1
        return original(scenario, output_directory)

    monkeypatch.setattr(
        "ems_simulator.terminal_value_robustness_matrix._run_fixed_control",
        counted,
    )

    result = run_terminal_value_robustness_matrix(tmp_path)

    assert calls == len(result.fixed_control_results) == 3


def test_exports_are_byte_deterministic(tmp_path: Path) -> None:
    first = run_terminal_value_robustness_matrix(tmp_path / "first")
    second = run_terminal_value_robustness_matrix(tmp_path / "second")

    assert all(
        left.read_text(encoding="utf-8") == right.read_text(encoding="utf-8")
        for left, right in zip(first.output_paths, second.output_paths, strict=True)
    )
    summary = first.evaluation_summary_path.read_text(encoding="utf-8")
    assert "larger terminal SOC divergence alone does not predict" in summary
    assert "not optimized terminal-value coefficients" in summary
