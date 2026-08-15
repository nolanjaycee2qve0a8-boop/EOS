"""Focused actual-state observation tests for TASK-165."""

from pathlib import Path

import pytest

from ems_simulator.terminal_soc_divergence_economic_demo import (
    run_terminal_soc_divergence_evaluation,
    scenario_definition,
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
    """Count TASK-162 calls without changing its valuation semantics."""

    __slots__ = ("calls",)

    def __init__(self) -> None:
        self.calls: list[TerminalEnergyValueInput] = []

    def calculate(
        self,
        value_input: TerminalEnergyValueInput,
    ) -> TerminalEnergyValueEvidence:
        self.calls.append(value_input)
        return super().calculate(value_input)


class CountingEconomicOutcomeCalculator(DeterministicEconomicOutcomeCalculator):
    """Count TASK-163 calls without changing its net-cost semantics."""

    __slots__ = ("calls",)

    def __init__(self) -> None:
        self.calls: list[EconomicOutcomeInput] = []

    def calculate(self, outcome_input: EconomicOutcomeInput) -> EconomicOutcomeEvidence:
        self.calls.append(outcome_input)
        return super().calculate(outcome_input)


def test_scenario_has_meaningful_24h_negative_margin_structure() -> None:
    scenario = scenario_definition()

    assert scenario.initial_soc == 0.50
    assert scenario.pv_cap_kw == 0.60
    assert len(scenario.tariff_profile_cny_per_kwh) == 24
    assert scenario.tariff_profile_cny_per_kwh[:6] == (0.80,) * 6
    assert scenario.tariff_profile_cny_per_kwh[6:] == (0.85,) * 18


def test_existing_paths_produce_actual_terminal_soc_divergence(tmp_path: Path) -> None:
    result = run_terminal_soc_divergence_evaluation(tmp_path)

    assert len(result.schedule_result.step_traces) == 24
    assert len(result.economic_result.step_traces) == 24
    assert result.first_divergence_index == 0
    assert result.first_divergence_timestamp == "2026-02-01T00:00:00+00:00"
    assert result.schedule.source_metrics.final_soc == pytest.approx(1.0)
    assert result.economic.source_metrics.final_soc == pytest.approx(0.5)
    assert result.deltas_economic_minus_schedule.final_soc == pytest.approx(-0.5)
    assert all(
        trace.simulation_trace.state.pv_result.actual_power_kw
        <= trace.simulation_trace.state.load_result.actual_power_kw
        for trace in result.schedule_result.step_traces
    )


def test_terminal_and_outcome_evidence_are_exact_and_called_once_per_path(
    tmp_path: Path,
) -> None:
    terminal_calculator = CountingTerminalValueCalculator()
    outcome_calculator = CountingEconomicOutcomeCalculator()
    result = run_terminal_soc_divergence_evaluation(
        tmp_path,
        terminal_calculator,
        outcome_calculator,
    )

    assert len(terminal_calculator.calls) == 2
    assert len(outcome_calculator.calls) == 2
    schedule_terminal = result.schedule.terminal_energy_value_evidence
    economic_terminal = result.economic.terminal_energy_value_evidence
    assert (
        schedule_terminal.source_input.terminal_soc
        == result.schedule.source_metrics.final_soc
    )
    assert (
        economic_terminal.source_input.terminal_soc
        == result.economic.source_metrics.final_soc
    )
    assert (
        schedule_terminal.source_input.battery_model
        is economic_terminal.source_input.battery_model
    )
    assert (
        schedule_terminal.source_input.valuation_import_price
        == economic_terminal.source_input.valuation_import_price
        == 0.85
    )
    assert (
        result.schedule.economic_outcome_evidence.terminal_energy_value_evidence
        is schedule_terminal
    )
    assert (
        result.economic.economic_outcome_evidence.terminal_energy_value_evidence
        is economic_terminal
    )


def test_terminal_value_shrinks_but_does_not_reverse_realized_cost_advantage(
    tmp_path: Path,
) -> None:
    result = run_terminal_soc_divergence_evaluation(tmp_path)
    schedule = result.schedule
    economic = result.economic
    deltas = result.deltas_economic_minus_schedule

    assert schedule.economic_outcome_evidence.realized_import_cost == pytest.approx(
        22.840526315789482
    )
    assert economic.economic_outcome_evidence.realized_import_cost == pytest.approx(
        18.63
    )
    assert (
        schedule.terminal_energy_value_evidence.terminal_energy_value
        == pytest.approx(6.46)
    )
    assert (
        economic.terminal_energy_value_evidence.terminal_energy_value
        == pytest.approx(2.4225)
    )
    assert schedule.economic_outcome_evidence.net_economic_cost == pytest.approx(
        16.380526315789483
    )
    assert economic.economic_outcome_evidence.net_economic_cost == pytest.approx(
        16.2075
    )
    assert deltas.realized_import_cost == pytest.approx(-4.210526315789482)
    assert deltas.terminal_energy_value == pytest.approx(-4.0375)
    assert deltas.net_economic_cost == pytest.approx(-0.17302631578948357)
    assert abs(deltas.net_economic_cost) < abs(deltas.realized_import_cost)
    assert deltas.net_economic_cost < 0.0


def test_exports_are_deterministic_and_hourly_evidence_shows_the_gate(
    tmp_path: Path,
) -> None:
    first = run_terminal_soc_divergence_evaluation(tmp_path / "first")
    second = run_terminal_soc_divergence_evaluation(tmp_path / "second")

    first_paths = (
        first.comparison_csv_path,
        first.hourly_trajectory_csv_path,
        first.daily_summary_path,
        first.soc_divergence_svg_path,
        first.realized_vs_terminal_value_svg_path,
        first.net_economic_cost_svg_path,
    )
    second_paths = (
        second.comparison_csv_path,
        second.hourly_trajectory_csv_path,
        second.daily_summary_path,
        second.soc_divergence_svg_path,
        second.realized_vs_terminal_value_svg_path,
        second.net_economic_cost_svg_path,
    )
    assert all(
        left.read_text(encoding="utf-8") == right.read_text(encoding="utf-8")
        for left, right in zip(first_paths, second_paths, strict=True)
    )
    hourly_rows = first.hourly_trajectory_csv_path.read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(hourly_rows) == 25
    assert "negative" in hourly_rows[1]
    assert "0.785000" in hourly_rows[1]
    assert "0.500000" in hourly_rows[1]
    assert (
        "shrinks the realized import-cost conclusion"
        in first.daily_summary_path.read_text(encoding="utf-8")
    )
