"""Regression tests for TASK-164 terminal-value-adjusted re-evaluation."""

import ast
from pathlib import Path

import pytest

from ems_simulator.terminal_value_economic_comparison_demo import (
    TerminalValueEconomicScenarioResult,
    run_terminal_value_evaluation,
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
    """Test double proving exactly one TASK-162 call per scenario/path."""

    __slots__ = ("calls",)

    def __init__(self) -> None:
        self.calls: list[TerminalEnergyValueInput] = []

    def calculate(
        self, value_input: TerminalEnergyValueInput
    ) -> TerminalEnergyValueEvidence:
        self.calls.append(value_input)
        return super().calculate(value_input)


class CountingEconomicOutcomeCalculator(DeterministicEconomicOutcomeCalculator):
    """Test double proving exactly one TASK-163 call per scenario/path."""

    __slots__ = ("calls",)

    def __init__(self) -> None:
        self.calls: list[EconomicOutcomeInput] = []

    def calculate(self, outcome_input: EconomicOutcomeInput) -> EconomicOutcomeEvidence:
        self.calls.append(outcome_input)
        return super().calculate(outcome_input)


def _by_id(tmp_path: Path) -> dict[str, TerminalValueEconomicScenarioResult]:
    result = run_terminal_value_evaluation(tmp_path)
    return {
        item.source_task_161_result.scenario.scenario_id: item
        for item in result.scenario_results
    }


def test_reuses_exact_task_161_e0_e1_e2_paths_and_actual_terminal_state(
    tmp_path: Path,
) -> None:
    results = _by_id(tmp_path)

    assert tuple(results) == ("E0", "E1", "E2")
    for item in results.values():
        source = item.source_task_161_result
        assert item.schedule.source_metrics is source.schedule_metrics
        assert item.economic.source_metrics is source.economic_metrics
        assert (
            item.schedule.terminal_energy_value_evidence.source_input.terminal_soc
            == source.schedule_metrics.final_soc
        )
        assert (
            item.economic.terminal_energy_value_evidence.source_input.terminal_soc
            == source.economic_metrics.final_soc
        )
        assert (
            item.schedule.terminal_energy_value_evidence.source_input.battery_model
            is item.economic.terminal_energy_value_evidence.source_input.battery_model
        )
        schedule_terminal_input = (
            item.schedule.terminal_energy_value_evidence.source_input
        )
        economic_terminal_input = (
            item.economic.terminal_energy_value_evidence.source_input
        )
        schedule_valuation = schedule_terminal_input.valuation_import_price
        economic_valuation = economic_terminal_input.valuation_import_price
        assert schedule_valuation == economic_valuation == item.valuation_import_price


def test_calls_task_162_and_task_163_exactly_once_per_scenario_path(
    tmp_path: Path,
) -> None:
    terminal_calculator = CountingTerminalValueCalculator()
    outcome_calculator = CountingEconomicOutcomeCalculator()
    result = run_terminal_value_evaluation(
        tmp_path,
        terminal_calculator,
        outcome_calculator,
    )

    assert len(result.scenario_results) == 3
    assert len(terminal_calculator.calls) == 6
    assert len(outcome_calculator.calls) == 6
    for item in result.scenario_results:
        assert (
            item.schedule.economic_outcome_evidence.terminal_energy_value_evidence
            is item.schedule.terminal_energy_value_evidence
        )
        assert (
            item.economic.economic_outcome_evidence.terminal_energy_value_evidence
            is item.economic.terminal_energy_value_evidence
        )


def test_e0_is_terminal_value_and_net_cost_neutral(tmp_path: Path) -> None:
    e0 = _by_id(tmp_path)["E0"]

    assert e0.schedule.economic_outcome_evidence.realized_import_cost == pytest.approx(
        5.174488
    )
    assert e0.economic.economic_outcome_evidence.realized_import_cost == pytest.approx(
        5.174488
    )
    assert e0.schedule.terminal_energy_value_evidence.terminal_energy_value == 0.0
    assert e0.economic.terminal_energy_value_evidence.terminal_energy_value == 0.0
    assert e0.deltas_economic_minus_schedule.net_economic_cost == 0.0


@pytest.mark.parametrize(
    ("scenario_id", "schedule_cost", "economic_cost", "terminal_value"),
    (
        ("E1", 17.322950, 16.505000, 6.460000),
        ("E2", 17.865706, 17.047756, 6.736842),
    ),
)
def test_e1_and_e2_preserve_realized_cost_advantage_when_terminal_soc_matches(
    tmp_path: Path,
    scenario_id: str,
    schedule_cost: float,
    economic_cost: float,
    terminal_value: float,
) -> None:
    item = _by_id(tmp_path)[scenario_id]

    assert (
        item.schedule.economic_outcome_evidence.realized_import_cost
        == pytest.approx(schedule_cost)
    )
    assert (
        item.economic.economic_outcome_evidence.realized_import_cost
        == pytest.approx(economic_cost)
    )
    assert (
        item.schedule.source_metrics.final_soc
        == item.economic.source_metrics.final_soc
        == 1.0
    )
    assert (
        item.schedule.terminal_energy_value_evidence.terminal_energy_value
        == pytest.approx(terminal_value)
    )
    assert (
        item.economic.terminal_energy_value_evidence.terminal_energy_value
        == pytest.approx(terminal_value)
    )
    assert item.deltas_economic_minus_schedule.net_economic_cost == pytest.approx(
        item.deltas_economic_minus_schedule.realized_import_cost
    )
    assert item.deltas_economic_minus_schedule.net_economic_cost == pytest.approx(
        -0.817950
    )


def test_csv_summary_and_svgs_are_deterministic(tmp_path: Path) -> None:
    first = run_terminal_value_evaluation(tmp_path / "first")
    second = run_terminal_value_evaluation(tmp_path / "second")

    first_paths = (
        first.summary_csv_path,
        first.daily_summary_path,
        first.realized_import_cost_svg_path,
        first.terminal_energy_value_svg_path,
        first.net_economic_cost_svg_path,
    )
    second_paths = (
        second.summary_csv_path,
        second.daily_summary_path,
        second.realized_import_cost_svg_path,
        second.terminal_energy_value_svg_path,
        second.net_economic_cost_svg_path,
    )
    assert all(
        left.read_text(encoding="utf-8") == right.read_text(encoding="utf-8")
        for left, right in zip(first_paths, second_paths, strict=True)
    )
    assert "delta_net_economic_cost" in first.summary_csv_path.read_text(
        encoding="utf-8"
    )
    assert "not full profit" in first.daily_summary_path.read_text(encoding="utf-8")


def test_module_only_composes_task_161_and_terminal_value_evidence() -> None:
    source = Path("ems_simulator/terminal_value_economic_comparison_demo.py").read_text(
        encoding="utf-8"
    )
    imports = {
        node.module or ""
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    }
    forbidden = (
        "ems_strategy",
        "forecast",
        "optimization.economic_planning",
        "optimization.economic_multi_opportunity_candidate_planning",
        "optimization.economic_multi_opportunity_physical_optimization",
        "simulator",
    )
    assert not any(
        module == prefix or module.startswith(f"{prefix}.")
        for module in imports
        for prefix in forbidden
    )
