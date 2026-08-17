"""TASK-173 auditable interval and daily economic ledger tests."""

from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

import pytest

import ems_simulator.economic_ledger as economic_ledger
from ems_simulator.economic_ledger import (
    DailyEconomicLedger,
    DeterministicEconomicLedgerBuilder,
    EconomicLedgerInput,
    EconomicLedgerInterval,
    _simulation_traces,
    run_reference_ledger,
)
from ems_simulator.economic_schedule_aware_comparison_demo import run_comparison
from ems_simulator.terminal_soc_divergence_economic_demo import (
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
    ExtendedEconomicOutcomeEvidence,
    ExtendedEconomicOutcomeInput,
    ImportCostEvidence,
    ImportCostInput,
    TerminalEnergyValueEvidence,
    TerminalEnergyValueInput,
)


def _interval(
    import_energy: float,
    export_energy: float,
    throughput: float,
) -> EconomicLedgerInterval:
    """Build a direct one-hour ledger interval with exact TASK-169--171 evidence."""

    import_evidence = DeterministicImportCostCalculator().calculate(
        ImportCostInput(import_energy, 0.50)
    )
    export_evidence = DeterministicExportRevenueCalculator().calculate(
        ExportRevenueInput(export_energy, 0.20)
    )
    degradation_evidence = DeterministicBatteryDegradationCostCalculator().calculate(
        BatteryDegradationCostInput(throughput, 0.10)
    )
    return EconomicLedgerInterval(
        0,
        datetime(2026, 2, 1, tzinfo=UTC),
        1.0,
        1.0,
        0.0,
        import_energy,
        export_energy,
        throughput,
        0.50,
        0.50,
        0.50,
        0.20,
        0.10,
        import_evidence,
        export_evidence,
        degradation_evidence,
        import_evidence.realized_import_cost,
        export_evidence.realized_export_revenue,
        degradation_evidence.battery_degradation_cost,
        import_evidence.realized_import_cost
        - export_evidence.realized_export_revenue
        + degradation_evidence.battery_degradation_cost,
    )


@pytest.mark.parametrize(
    ("import_energy", "export_energy", "throughput"),
    (
        (3.0, 0.0, 0.0),
        (0.0, 4.0, 0.0),
        (0.0, 0.0, 2.0),
        (3.0, 4.0, 2.0),
        (0.0, 0.0, 0.0),
    ),
)
def test_interval_formula_and_evidence_identity(
    import_energy: float,
    export_energy: float,
    throughput: float,
) -> None:
    interval = _interval(import_energy, export_energy, throughput)

    assert interval.realized_import_cost == pytest.approx(import_energy * 0.50)
    assert interval.realized_export_revenue == pytest.approx(export_energy * 0.20)
    assert interval.battery_degradation_cost == pytest.approx(throughput * 0.10)
    assert interval.realized_interval_net_cost == pytest.approx(
        import_energy * 0.50 - export_energy * 0.20 + throughput * 0.10
    )
    assert interval.import_cost_evidence.source_input.realized_import_energy_kwh == (
        import_energy
    )
    assert interval.export_revenue_evidence.source_input.realized_export_energy_kwh == (
        export_energy
    )
    assert (
        interval.battery_degradation_cost_evidence.source_input.battery_throughput_kwh
        == throughput
    )
    assert not hasattr(interval, "__dict__")


def test_builder_reads_actual_grid_sign_and_absolute_actual_battery_power(
    tmp_path: Path,
) -> None:
    comparison = run_comparison(tmp_path / "task161")
    source = next(
        item
        for item in comparison.scenario_results
        if item.scenario.scenario_id == "E1"
    )
    trajectory = source.schedule_result
    ledger_input = EconomicLedgerInput(
        trajectory,
        (0.20,) * 24,
        (0.05,) * 24,
        0.85,
        source.schedule_input.daily_mpc_input.battery_optimization_model,
    )
    ledger = DeterministicEconomicLedgerBuilder().build(ledger_input)

    assert ledger.source_input is ledger_input
    assert ledger.source_input.source_trajectory is trajectory
    assert ledger.total_grid_import_energy_kwh > 0.0
    assert ledger.total_grid_export_energy_kwh > 0.0
    for trace, interval in zip(
        _simulation_traces(trajectory), ledger.intervals, strict=True
    ):
        state = trace.state
        duration_hours = trace.simulation_input.step_identity.duration_seconds / 3600.0
        grid_power = state.grid_result.actual_grid_power_kw
        assert interval.grid_import_energy_kwh == pytest.approx(
            max(grid_power, 0.0) * duration_hours
        )
        assert interval.grid_export_energy_kwh == pytest.approx(
            max(-grid_power, 0.0) * duration_hours
        )
        assert interval.battery_throughput_kwh == pytest.approx(
            abs(state.battery_result.actual_power_kw) * duration_hours
        )


def test_builder_does_not_rerun_or_mutate_completed_trajectory(tmp_path: Path) -> None:
    completed = run_terminal_soc_divergence_evaluation(tmp_path / "fixed")
    source = completed.schedule_result
    model = completed.schedule_input.daily_mpc_input.battery_optimization_model
    source_trace_ids = tuple(id(trace) for trace in source.step_traces)
    source_grid_and_soc = tuple(
        (
            trace.simulation_trace.state.grid_result.actual_grid_power_kw,
            trace.simulation_trace.state.battery_result.next_state.soc,
        )
        for trace in source.step_traces
    )
    builder = DeterministicEconomicLedgerBuilder()

    first = builder.build(
        EconomicLedgerInput(source, (0.20,) * 24, (0.05,) * 24, 0.85, model)
    )
    second = builder.build(
        EconomicLedgerInput(source, (0.60,) * 24, (0.10,) * 24, 0.90, model)
    )

    assert first.source_input.source_trajectory is source
    assert second.source_input.source_trajectory is source
    assert tuple(id(trace) for trace in source.step_traces) == source_trace_ids
    assert (
        tuple(
            (
                trace.simulation_trace.state.grid_result.actual_grid_power_kw,
                trace.simulation_trace.state.battery_result.next_state.soc,
            )
            for trace in source.step_traces
        )
        == source_grid_and_soc
    )
    assert second.total_realized_export_revenue >= first.total_realized_export_revenue


def test_reference_ledger_reconciles_once_per_interval_and_once_per_day(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CountingImportCalculator(DeterministicImportCostCalculator):
        calls: ClassVar[int] = 0

        def calculate(self, value_input: ImportCostInput) -> ImportCostEvidence:
            type(self).calls += 1
            return super().calculate(value_input)

    class CountingExportCalculator(DeterministicExportRevenueCalculator):
        calls: ClassVar[int] = 0

        def calculate(self, value_input: ExportRevenueInput) -> ExportRevenueEvidence:
            type(self).calls += 1
            return super().calculate(value_input)

    class CountingDegradationCalculator(DeterministicBatteryDegradationCostCalculator):
        calls: ClassVar[int] = 0

        def calculate(
            self,
            value_input: BatteryDegradationCostInput,
        ) -> BatteryDegradationCostEvidence:
            type(self).calls += 1
            return super().calculate(value_input)

    class CountingTerminalCalculator(DeterministicTerminalEnergyValueCalculator):
        calls: ClassVar[int] = 0

        def calculate(
            self,
            value_input: TerminalEnergyValueInput,
        ) -> TerminalEnergyValueEvidence:
            type(self).calls += 1
            return super().calculate(value_input)

    class CountingOutcomeCalculator(DeterministicExtendedEconomicOutcomeCalculator):
        calls: ClassVar[int] = 0

        def calculate(
            self,
            outcome_input: ExtendedEconomicOutcomeInput,
        ) -> ExtendedEconomicOutcomeEvidence:
            type(self).calls += 1
            return super().calculate(outcome_input)

    monkeypatch.setattr(
        economic_ledger,
        "DeterministicImportCostCalculator",
        CountingImportCalculator,
    )
    monkeypatch.setattr(
        economic_ledger,
        "DeterministicExportRevenueCalculator",
        CountingExportCalculator,
    )
    monkeypatch.setattr(
        economic_ledger,
        "DeterministicBatteryDegradationCostCalculator",
        CountingDegradationCalculator,
    )
    monkeypatch.setattr(
        economic_ledger,
        "DeterministicTerminalEnergyValueCalculator",
        CountingTerminalCalculator,
    )
    monkeypatch.setattr(
        economic_ledger,
        "DeterministicExtendedEconomicOutcomeCalculator",
        CountingOutcomeCalculator,
    )

    result = run_reference_ledger(tmp_path)
    ledger = result.ledger

    assert len(ledger.intervals) == 24
    assert CountingImportCalculator.calls == 24
    assert CountingExportCalculator.calls == 24
    assert CountingDegradationCalculator.calls == 24
    assert CountingTerminalCalculator.calls == 1
    assert CountingOutcomeCalculator.calls == 1
    assert ledger.final_soc_fraction == pytest.approx(1.0)
    assert ledger.total_realized_import_cost == pytest.approx(22.840526315789482)
    assert ledger.total_battery_degradation_cost == pytest.approx(0.2631578947368421)
    assert ledger.terminal_energy_value == pytest.approx(6.46)
    assert ledger.adjusted_net_economic_cost == pytest.approx(16.64368421052632)
    assert (
        ledger.extended_outcome_evidence.terminal_energy_value_evidence
        is ledger.terminal_energy_value_evidence
    )
    assert ledger.terminal_energy_value_evidence.source_input.battery_model is (
        ledger.source_input.battery_model
    )
    assert result.intervals_csv_path.exists()
    assert result.daily_csv_path.exists()
    assert result.summary_path.exists()
    assert "Terminal value is one horizon-end credit" in result.summary_path.read_text(
        encoding="utf-8"
    )


def test_reference_output_is_byte_deterministic(tmp_path: Path) -> None:
    first = run_reference_ledger(tmp_path / "first")
    second = run_reference_ledger(tmp_path / "second")

    assert type(first.ledger) is DailyEconomicLedger
    assert all(
        left.read_text(encoding="utf-8") == right.read_text(encoding="utf-8")
        for left, right in zip(
            (
                first.intervals_csv_path,
                first.daily_csv_path,
                first.summary_path,
            ),
            (
                second.intervals_csv_path,
                second.daily_csv_path,
                second.summary_path,
            ),
            strict=True,
        )
    )
