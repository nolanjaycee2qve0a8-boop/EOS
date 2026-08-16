"""TASK-172 fixed-control extended accounting evaluation tests."""

from pathlib import Path

import pytest

import ems_simulator.extended_economic_re_evaluation as re_evaluation
from ems_simulator.economic_schedule_aware_comparison_demo import (
    EconomicScheduleAwareComparisonResult,
    run_comparison,
)
from ems_simulator.extended_economic_re_evaluation import (
    ExtendedEconomicEvaluation,
    ExtendedEconomicReEvaluationResult,
    _pair_delta,
    run_extended_economic_re_evaluation,
)
from ems_simulator.terminal_soc_divergence_economic_demo import (
    TerminalSOCDivergenceResult,
    run_terminal_soc_divergence_evaluation,
)
from optimization import (
    BatteryDegradationCostEvidence,
    BatteryDegradationCostInput,
    DeterministicBatteryDegradationCostCalculator,
    DeterministicExportRevenueCalculator,
    DeterministicExtendedEconomicOutcomeCalculator,
    DeterministicImportCostCalculator,
    DeterministicTerminalEnergyValueCalculator,
    ExportRevenueEvidence,
    ExportRevenueInput,
    ExtendedEconomicOutcomeInput,
    ImportCostInput,
    TerminalEnergyValueEvidence,
    TerminalEnergyValueInput,
)


def _by_key(
    result: ExtendedEconomicReEvaluationResult,
    scenario_id: str,
    path: str,
    export_tariff: float,
    degradation_rate: float,
    terminal_price: float,
) -> ExtendedEconomicEvaluation:
    return next(
        evaluation
        for evaluation in result.evaluations
        if (
            evaluation.fixed_path.scenario_id == scenario_id
            and evaluation.fixed_path.path == path
            and evaluation.export_revenue_evidence.export_tariff_per_kwh
            == export_tariff
            and (
                evaluation.battery_degradation_cost_evidence.degradation_cost_per_throughput_kwh
                == degradation_rate
            )
            and evaluation.terminal_energy_value_evidence.valuation_import_price
            == terminal_price
        )
    )


def test_runs_fixed_controls_once_then_expands_accounting_sensitivities(
    tmp_path: Path,
) -> None:
    comparison_calls: list[Path] = []
    divergence_calls: list[Path] = []

    def comparison_runner(path: Path) -> EconomicScheduleAwareComparisonResult:
        comparison_calls.append(path)
        return run_comparison(path)

    def divergence_runner(path: Path) -> TerminalSOCDivergenceResult:
        divergence_calls.append(path)
        return run_terminal_soc_divergence_evaluation(path)

    result = run_extended_economic_re_evaluation(
        tmp_path,
        comparison_runner,
        divergence_runner,
    )

    assert len(comparison_calls) == 1
    assert len(divergence_calls) == 1
    assert len(result.fixed_paths) == 8
    assert len(result.evaluations) == 8 * 2 * 3 * 5
    assert tuple(path.scenario_id for path in result.fixed_paths) == (
        "E0",
        "E0",
        "E1",
        "E1",
        "E2",
        "E2",
        "C_TERMINAL_SOC_DIVERGENCE",
        "C_TERMINAL_SOC_DIVERGENCE",
    )
    assert result.scenario_summary_path.exists()
    assert result.sensitivity_matrix_path.exists()
    assert result.daily_summary_path.exists()


def test_accounting_evidence_identity_sensitivity_and_decomposition(
    tmp_path: Path,
) -> None:
    result = run_extended_economic_re_evaluation(tmp_path)
    schedule = _by_key(result, "E1", "Schedule", 0.20, 0.05, 0.85)
    economic = _by_key(result, "E1", "Economic", 0.20, 0.05, 0.85)
    high_export = _by_key(result, "E1", "Schedule", 0.60, 0.05, 0.85)
    zero_degradation = _by_key(result, "E1", "Schedule", 0.20, 0.00, 0.85)
    zero_terminal = _by_key(result, "E1", "Schedule", 0.20, 0.05, 0.00)
    same_export = _by_key(result, "E1", "Schedule", 0.20, 0.10, 0.90)
    same_degradation = _by_key(result, "E1", "Schedule", 0.60, 0.05, 0.90)
    same_terminal = _by_key(result, "E1", "Schedule", 0.60, 0.10, 0.85)

    assert (
        schedule.extended_outcome_evidence.terminal_energy_value_evidence
        is schedule.terminal_energy_value_evidence
    )
    assert (
        schedule.terminal_energy_value_evidence.source_input.battery_model
        is schedule.fixed_path.battery_model
    )
    assert schedule.export_revenue_evidence.source_input.realized_export_energy_kwh == (
        schedule.fixed_path.source_metrics.grid_export_energy_kwh
    )
    assert (
        schedule.battery_degradation_cost_evidence.source_input.battery_throughput_kwh
        == (schedule.fixed_path.source_metrics.battery_throughput_kwh)
    )
    assert high_export.fixed_path is schedule.fixed_path
    assert same_export.export_revenue_evidence is schedule.export_revenue_evidence
    assert (
        same_degradation.battery_degradation_cost_evidence
        is schedule.battery_degradation_cost_evidence
    )
    assert (
        same_terminal.terminal_energy_value_evidence
        is schedule.terminal_energy_value_evidence
    )
    assert high_export.extended_outcome_evidence.realized_import_cost == (
        schedule.extended_outcome_evidence.realized_import_cost
    )
    assert high_export.battery_degradation_cost_evidence.battery_degradation_cost == (
        schedule.battery_degradation_cost_evidence.battery_degradation_cost
    )
    assert high_export.terminal_energy_value_evidence.terminal_energy_value == (
        schedule.terminal_energy_value_evidence.terminal_energy_value
    )
    assert (
        zero_degradation.battery_degradation_cost_evidence.battery_degradation_cost
        == 0.0
    )
    assert zero_terminal.terminal_energy_value_evidence.terminal_energy_value == 0.0
    assert _pair_delta(schedule, economic)[4] == pytest.approx(
        _pair_delta(schedule, economic)[0]
        - _pair_delta(schedule, economic)[1]
        + _pair_delta(schedule, economic)[2]
        - _pair_delta(schedule, economic)[3]
    )


def test_task_165_trajectory_and_scalar_import_cost_compatibility(
    tmp_path: Path,
) -> None:
    result = run_extended_economic_re_evaluation(tmp_path)
    schedule = _by_key(
        result, "C_TERMINAL_SOC_DIVERGENCE", "Schedule", 0.20, 0.05, 0.85
    )
    economic = _by_key(
        result, "C_TERMINAL_SOC_DIVERGENCE", "Economic", 0.20, 0.05, 0.85
    )
    scalar_import = DeterministicImportCostCalculator().calculate(
        ImportCostInput(10.0, 0.60)
    )
    compatible_outcome = DeterministicExtendedEconomicOutcomeCalculator().calculate(
        ExtendedEconomicOutcomeInput(
            scalar_import.realized_import_cost,
            0.0,
            0.0,
            schedule.terminal_energy_value_evidence,
        )
    )

    assert schedule.fixed_path.source_metrics.final_soc == pytest.approx(1.0)
    assert economic.fixed_path.source_metrics.final_soc == pytest.approx(0.5)
    assert schedule.extended_outcome_evidence.realized_export_revenue == 0.0
    assert economic.extended_outcome_evidence.realized_export_revenue == 0.0
    assert scalar_import.realized_import_cost == pytest.approx(6.0)
    assert compatible_outcome.realized_import_cost == pytest.approx(6.0)


def test_evidence_calculators_run_once_per_independent_assumption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CountingExportCalculator(DeterministicExportRevenueCalculator):
        calls = 0

        def calculate(self, revenue_input: ExportRevenueInput) -> ExportRevenueEvidence:
            type(self).calls += 1
            return super().calculate(revenue_input)

    class CountingDegradationCalculator(DeterministicBatteryDegradationCostCalculator):
        calls = 0

        def calculate(
            self,
            degradation_input: BatteryDegradationCostInput,
        ) -> BatteryDegradationCostEvidence:
            type(self).calls += 1
            return super().calculate(degradation_input)

    class CountingTerminalCalculator(DeterministicTerminalEnergyValueCalculator):
        calls = 0

        def calculate(
            self,
            value_input: TerminalEnergyValueInput,
        ) -> TerminalEnergyValueEvidence:
            type(self).calls += 1
            return super().calculate(value_input)

    monkeypatch.setattr(
        re_evaluation,
        "DeterministicExportRevenueCalculator",
        CountingExportCalculator,
    )
    monkeypatch.setattr(
        re_evaluation,
        "DeterministicBatteryDegradationCostCalculator",
        CountingDegradationCalculator,
    )
    monkeypatch.setattr(
        re_evaluation,
        "DeterministicTerminalEnergyValueCalculator",
        CountingTerminalCalculator,
    )

    run_extended_economic_re_evaluation(tmp_path)

    assert CountingExportCalculator.calls == 8 * 2
    assert CountingDegradationCalculator.calls == 8 * 3
    assert CountingTerminalCalculator.calls == 8 * 5
