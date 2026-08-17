# ruff: noqa: E501
"""Auditable interval and daily economic ledger for completed trajectories.

The ledger reads completed simulator traces only.  It never runs a strategy,
MPC cycle, feasibility boundary, actuation handoff, or simulator step.
"""

import argparse
import csv
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from math import isclose, isfinite
from pathlib import Path

from ems_simulator.economic_multi_opportunity_explainable_mpc_daily import (
    EconomicMultiOpportunityExplainableMPCDailySimulationResult,
)
from ems_simulator.multi_opportunity_explainable_mpc_daily import (
    MultiOpportunityExplainableMPCDailySimulationResult,
)
from ems_simulator.runner import DailySimulationResult
from ems_simulator.terminal_soc_divergence_economic_demo import (
    run_terminal_soc_divergence_evaluation,
)
from optimization import (
    BatteryDegradationCostEvidence,
    BatteryDegradationCostInput,
    BatteryOptimizationModel,
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
from simulator import SimulationExecutionTrace

LedgerTrajectory = (
    DailySimulationResult
    | MultiOpportunityExplainableMPCDailySimulationResult
    | EconomicMultiOpportunityExplainableMPCDailySimulationResult
)


def _require_non_negative_finite(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized) or normalized < 0.0:
        raise ValueError(f"{field_name} must be finite and non-negative")
    return normalized


def _require_positive_finite(value: object, field_name: str) -> float:
    normalized = _require_non_negative_finite(value, field_name)
    if normalized == 0.0:
        raise ValueError(f"{field_name} must be greater than zero")
    return normalized


def _require_fraction(value: object, field_name: str) -> float:
    normalized = _require_non_negative_finite(value, field_name)
    if normalized > 1.0:
        raise ValueError(f"{field_name} must be at most one")
    return normalized


@dataclass(frozen=True, slots=True)
class EconomicLedgerInput:
    """Caller-owned assumptions applied to one already completed trajectory.

    Import tariff is intentionally absent: every trace retains its actual
    interval import tariff, which TASK-171 can settle truthfully. Export and
    degradation sequences are explicit accounting assumptions, not forecasts
    or optimization tariffs.
    """

    source_trajectory: LedgerTrajectory
    export_tariff_per_kwh: tuple[float, ...]
    degradation_cost_per_throughput_kwh: tuple[float, ...]
    terminal_valuation_price: float
    battery_model: BatteryOptimizationModel

    def __post_init__(self) -> None:
        if not isinstance(
            self.source_trajectory,
            DailySimulationResult
            | MultiOpportunityExplainableMPCDailySimulationResult
            | EconomicMultiOpportunityExplainableMPCDailySimulationResult,
        ):
            raise TypeError("source_trajectory must be a completed daily trajectory")
        if not isinstance(self.export_tariff_per_kwh, tuple):
            raise TypeError("export_tariff_per_kwh must be a tuple")
        if not isinstance(self.degradation_cost_per_throughput_kwh, tuple):
            raise TypeError("degradation_cost_per_throughput_kwh must be a tuple")
        trace_count = len(_simulation_traces(self.source_trajectory))
        if len(self.export_tariff_per_kwh) != trace_count:
            raise ValueError("export tariff sequence must match completed trace count")
        if len(self.degradation_cost_per_throughput_kwh) != trace_count:
            raise ValueError(
                "degradation rate sequence must match completed trace count"
            )
        object.__setattr__(
            self,
            "export_tariff_per_kwh",
            tuple(
                _require_non_negative_finite(value, "export_tariff_per_kwh")
                for value in self.export_tariff_per_kwh
            ),
        )
        object.__setattr__(
            self,
            "degradation_cost_per_throughput_kwh",
            tuple(
                _require_non_negative_finite(
                    value,
                    "degradation_cost_per_throughput_kwh",
                )
                for value in self.degradation_cost_per_throughput_kwh
            ),
        )
        object.__setattr__(
            self,
            "terminal_valuation_price",
            _require_non_negative_finite(
                self.terminal_valuation_price,
                "terminal_valuation_price",
            ),
        )
        if not isinstance(self.battery_model, BatteryOptimizationModel):
            raise TypeError("battery_model must be a BatteryOptimizationModel")


@dataclass(frozen=True, slots=True)
class EconomicLedgerInterval:
    """One immutable realized interval record; terminal value is excluded."""

    step_index: int
    timestamp: datetime
    duration_hours: float
    load_energy_kwh: float
    pv_energy_kwh: float
    grid_import_energy_kwh: float
    grid_export_energy_kwh: float
    battery_throughput_kwh: float
    soc_before_fraction: float
    soc_after_fraction: float
    import_tariff_per_kwh: float
    export_tariff_per_kwh: float
    degradation_cost_per_throughput_kwh: float
    import_cost_evidence: ImportCostEvidence
    export_revenue_evidence: ExportRevenueEvidence
    battery_degradation_cost_evidence: BatteryDegradationCostEvidence
    realized_import_cost: float
    realized_export_revenue: float
    battery_degradation_cost: float
    realized_interval_net_cost: float

    def __post_init__(self) -> None:
        if isinstance(self.step_index, bool) or not isinstance(self.step_index, int):
            raise TypeError("step_index must be an integer")
        if self.step_index < 0:
            raise ValueError("step_index must be non-negative")
        if not isinstance(self.timestamp, datetime) or self.timestamp.tzinfo is None:
            raise TypeError("timestamp must be timezone-aware datetime")
        for field_name in (
            "duration_hours",
            "load_energy_kwh",
            "pv_energy_kwh",
            "grid_import_energy_kwh",
            "grid_export_energy_kwh",
            "battery_throughput_kwh",
            "import_tariff_per_kwh",
            "export_tariff_per_kwh",
            "degradation_cost_per_throughput_kwh",
            "realized_import_cost",
            "realized_export_revenue",
            "battery_degradation_cost",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_non_negative_finite(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self,
            "duration_hours",
            _require_positive_finite(self.duration_hours, "duration_hours"),
        )
        for field_name in ("soc_before_fraction", "soc_after_fraction"):
            object.__setattr__(
                self,
                field_name,
                _require_fraction(getattr(self, field_name), field_name),
            )
        if not isinstance(self.import_cost_evidence, ImportCostEvidence):
            raise TypeError("import_cost_evidence must be an ImportCostEvidence")
        if not isinstance(self.export_revenue_evidence, ExportRevenueEvidence):
            raise TypeError("export_revenue_evidence must be an ExportRevenueEvidence")
        if not isinstance(
            self.battery_degradation_cost_evidence,
            BatteryDegradationCostEvidence,
        ):
            raise TypeError(
                "battery_degradation_cost_evidence must be a BatteryDegradationCostEvidence"
            )
        if (
            self.import_cost_evidence.realized_import_energy_kwh
            != self.grid_import_energy_kwh
            or self.import_cost_evidence.import_tariff_per_kwh
            != self.import_tariff_per_kwh
            or self.import_cost_evidence.realized_import_cost
            != self.realized_import_cost
        ):
            raise ValueError("import evidence must preserve interval input semantics")
        if (
            self.export_revenue_evidence.realized_export_energy_kwh
            != self.grid_export_energy_kwh
            or self.export_revenue_evidence.export_tariff_per_kwh
            != self.export_tariff_per_kwh
            or self.export_revenue_evidence.realized_export_revenue
            != self.realized_export_revenue
        ):
            raise ValueError("export evidence must preserve interval input semantics")
        if (
            self.battery_degradation_cost_evidence.battery_throughput_kwh
            != self.battery_throughput_kwh
            or self.battery_degradation_cost_evidence.degradation_cost_per_throughput_kwh
            != self.degradation_cost_per_throughput_kwh
            or self.battery_degradation_cost_evidence.battery_degradation_cost
            != self.battery_degradation_cost
        ):
            raise ValueError(
                "degradation evidence must preserve interval input semantics"
            )
        expected = (
            self.realized_import_cost
            - self.realized_export_revenue
            + self.battery_degradation_cost
        )
        if not isclose(
            self.realized_interval_net_cost,
            expected,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("realized_interval_net_cost must reconcile")
        object.__setattr__(self, "realized_interval_net_cost", float(expected))


@dataclass(frozen=True, slots=True)
class DailyEconomicLedger:
    """Daily reconciliation with one terminal credit outside normal intervals."""

    source_input: EconomicLedgerInput
    intervals: tuple[EconomicLedgerInterval, ...]
    total_load_energy_kwh: float
    total_pv_energy_kwh: float
    total_grid_import_energy_kwh: float
    total_grid_export_energy_kwh: float
    total_battery_throughput_kwh: float
    total_realized_import_cost: float
    total_realized_export_revenue: float
    total_battery_degradation_cost: float
    total_realized_net_cost: float
    final_soc_fraction: float
    terminal_energy_value_evidence: TerminalEnergyValueEvidence
    terminal_energy_value: float
    extended_outcome_evidence: ExtendedEconomicOutcomeEvidence
    adjusted_net_economic_cost: float

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, EconomicLedgerInput):
            raise TypeError("source_input must be an EconomicLedgerInput")
        if not isinstance(self.intervals, tuple) or not self.intervals:
            raise ValueError("intervals must be a non-empty tuple")
        if any(
            not isinstance(interval, EconomicLedgerInterval)
            for interval in self.intervals
        ):
            raise TypeError("intervals must contain EconomicLedgerInterval values")
        if not isinstance(
            self.terminal_energy_value_evidence,
            TerminalEnergyValueEvidence,
        ):
            raise TypeError(
                "terminal_energy_value_evidence must be a TerminalEnergyValueEvidence"
            )
        if not isinstance(
            self.extended_outcome_evidence, ExtendedEconomicOutcomeEvidence
        ):
            raise TypeError(
                "extended_outcome_evidence must be an ExtendedEconomicOutcomeEvidence"
            )
        if (
            self.extended_outcome_evidence.terminal_energy_value_evidence
            is not self.terminal_energy_value_evidence
        ):
            raise ValueError("extended outcome must retain exact terminal evidence")
        if (
            self.terminal_energy_value_evidence.source_input.battery_model
            is not self.source_input.battery_model
        ):
            raise ValueError("terminal evidence must retain exact battery model")
        for field_name in (
            "total_load_energy_kwh",
            "total_pv_energy_kwh",
            "total_grid_import_energy_kwh",
            "total_grid_export_energy_kwh",
            "total_battery_throughput_kwh",
            "total_realized_import_cost",
            "total_realized_export_revenue",
            "total_battery_degradation_cost",
            "total_realized_net_cost",
            "terminal_energy_value",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_non_negative_finite(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self,
            "final_soc_fraction",
            _require_fraction(self.final_soc_fraction, "final_soc_fraction"),
        )
        expected_totals = (
            sum(item.load_energy_kwh for item in self.intervals),
            sum(item.pv_energy_kwh for item in self.intervals),
            sum(item.grid_import_energy_kwh for item in self.intervals),
            sum(item.grid_export_energy_kwh for item in self.intervals),
            sum(item.battery_throughput_kwh for item in self.intervals),
            sum(item.realized_import_cost for item in self.intervals),
            sum(item.realized_export_revenue for item in self.intervals),
            sum(item.battery_degradation_cost for item in self.intervals),
            sum(item.realized_interval_net_cost for item in self.intervals),
        )
        actual_totals = (
            self.total_load_energy_kwh,
            self.total_pv_energy_kwh,
            self.total_grid_import_energy_kwh,
            self.total_grid_export_energy_kwh,
            self.total_battery_throughput_kwh,
            self.total_realized_import_cost,
            self.total_realized_export_revenue,
            self.total_battery_degradation_cost,
            self.total_realized_net_cost,
        )
        if any(
            not isclose(actual, expected, rel_tol=0.0, abs_tol=1e-12)
            for actual, expected in zip(actual_totals, expected_totals, strict=True)
        ):
            raise ValueError("daily ledger totals must reconcile with intervals")
        expected_net = (
            self.total_realized_import_cost
            - self.total_realized_export_revenue
            + self.total_battery_degradation_cost
        )
        if not isclose(
            self.total_realized_net_cost,
            expected_net,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("total_realized_net_cost must reconcile")
        if (
            self.terminal_energy_value
            != self.terminal_energy_value_evidence.terminal_energy_value
        ):
            raise ValueError("terminal value must retain exact terminal evidence value")
        if (
            self.extended_outcome_evidence.realized_import_cost
            != self.total_realized_import_cost
            or self.extended_outcome_evidence.realized_export_revenue
            != self.total_realized_export_revenue
            or self.extended_outcome_evidence.battery_degradation_cost
            != self.total_battery_degradation_cost
            or self.extended_outcome_evidence.adjusted_net_economic_cost
            != self.adjusted_net_economic_cost
        ):
            raise ValueError(
                "extended outcome must retain exact daily accounting values"
            )
        expected_adjusted = self.total_realized_net_cost - self.terminal_energy_value
        if not isclose(
            self.adjusted_net_economic_cost,
            expected_adjusted,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("adjusted_net_economic_cost must reconcile")


class EconomicLedgerBoundary(ABC):
    """Define a stateless completed-trajectory accounting seam."""

    __slots__ = ()

    @abstractmethod
    def build(self, ledger_input: EconomicLedgerInput) -> DailyEconomicLedger:
        """Read completed traces and return one reconciling daily ledger."""
        raise NotImplementedError


class DeterministicEconomicLedgerBuilder(EconomicLedgerBoundary):
    """Build interval evidence and a daily TASK-168 reconciliation once."""

    __slots__ = ()

    def build(self, ledger_input: EconomicLedgerInput) -> DailyEconomicLedger:
        if not isinstance(ledger_input, EconomicLedgerInput):
            raise TypeError("ledger_input must be an EconomicLedgerInput")
        import_calculator = DeterministicImportCostCalculator()
        export_calculator = DeterministicExportRevenueCalculator()
        degradation_calculator = DeterministicBatteryDegradationCostCalculator()
        intervals = tuple(
            _build_interval(
                index,
                trace,
                ledger_input.export_tariff_per_kwh[index],
                ledger_input.degradation_cost_per_throughput_kwh[index],
                import_calculator,
                export_calculator,
                degradation_calculator,
            )
            for index, trace in enumerate(
                _simulation_traces(ledger_input.source_trajectory)
            )
        )
        final_soc = intervals[-1].soc_after_fraction
        terminal_evidence = DeterministicTerminalEnergyValueCalculator().calculate(
            TerminalEnergyValueInput(
                final_soc,
                ledger_input.battery_model,
                ledger_input.terminal_valuation_price,
            )
        )
        total_import = sum(item.realized_import_cost for item in intervals)
        total_export = sum(item.realized_export_revenue for item in intervals)
        total_degradation = sum(item.battery_degradation_cost for item in intervals)
        outcome = DeterministicExtendedEconomicOutcomeCalculator().calculate(
            ExtendedEconomicOutcomeInput(
                total_import,
                total_export,
                total_degradation,
                terminal_evidence,
            )
        )
        return DailyEconomicLedger(
            ledger_input,
            intervals,
            sum(item.load_energy_kwh for item in intervals),
            sum(item.pv_energy_kwh for item in intervals),
            sum(item.grid_import_energy_kwh for item in intervals),
            sum(item.grid_export_energy_kwh for item in intervals),
            sum(item.battery_throughput_kwh for item in intervals),
            total_import,
            total_export,
            total_degradation,
            sum(item.realized_interval_net_cost for item in intervals),
            final_soc,
            terminal_evidence,
            terminal_evidence.terminal_energy_value,
            outcome,
            outcome.adjusted_net_economic_cost,
        )


def _simulation_traces(
    source_trajectory: LedgerTrajectory,
) -> tuple[SimulationExecutionTrace, ...]:
    if isinstance(source_trajectory, DailySimulationResult):
        return source_trajectory.traces
    if isinstance(
        source_trajectory, MultiOpportunityExplainableMPCDailySimulationResult
    ):
        return tuple(item.simulation_trace for item in source_trajectory.step_traces)
    if isinstance(
        source_trajectory,
        EconomicMultiOpportunityExplainableMPCDailySimulationResult,
    ):
        return tuple(item.simulation_trace for item in source_trajectory.step_traces)
    raise TypeError("source_trajectory must be a completed daily trajectory")


def _build_interval(
    index: int,
    trace: SimulationExecutionTrace,
    export_tariff: float,
    degradation_rate: float,
    import_calculator: DeterministicImportCostCalculator,
    export_calculator: DeterministicExportRevenueCalculator,
    degradation_calculator: DeterministicBatteryDegradationCostCalculator,
) -> EconomicLedgerInterval:
    state = trace.state
    identity = trace.simulation_input.step_identity
    if identity.timestamp is None:
        raise ValueError("ledger interval requires an explicit timestamp")
    duration_hours = identity.duration_seconds / 3600.0
    grid_power = state.grid_result.actual_grid_power_kw
    import_energy = max(grid_power, 0.0) * duration_hours
    export_energy = max(-grid_power, 0.0) * duration_hours
    throughput = abs(state.battery_result.actual_power_kw) * duration_hours
    import_tariff = state.tariff_result.import_price_cny_per_kwh
    import_evidence = import_calculator.calculate(
        ImportCostInput(import_energy, import_tariff)
    )
    export_evidence = export_calculator.calculate(
        ExportRevenueInput(export_energy, export_tariff)
    )
    degradation_evidence = degradation_calculator.calculate(
        BatteryDegradationCostInput(throughput, degradation_rate)
    )
    return EconomicLedgerInterval(
        index,
        identity.timestamp,
        duration_hours,
        state.load_result.actual_power_kw * duration_hours,
        state.pv_result.actual_power_kw * duration_hours,
        import_energy,
        export_energy,
        throughput,
        state.battery_result.simulation_input.source_state.soc,
        state.battery_result.next_state.soc,
        import_tariff,
        export_tariff,
        degradation_rate,
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


@dataclass(frozen=True, slots=True)
class EconomicLedgerReferenceResult:
    """Reference C Schedule ledger and its deterministic output files."""

    source_trajectory: MultiOpportunityExplainableMPCDailySimulationResult
    ledger: DailyEconomicLedger
    intervals_csv_path: Path
    daily_csv_path: Path
    summary_path: Path


def run_reference_ledger(output_directory: Path) -> EconomicLedgerReferenceResult:
    """Build one ledger after reusing the completed TASK-165 Schedule trajectory."""

    if not isinstance(output_directory, Path):
        raise TypeError("output_directory must be a pathlib.Path")
    output_directory.mkdir(parents=True, exist_ok=True)
    reference = run_terminal_soc_divergence_evaluation(
        output_directory / "task165_fixed_trajectory"
    )
    source = reference.schedule_result
    model = reference.schedule_input.daily_mpc_input.battery_optimization_model
    ledger = DeterministicEconomicLedgerBuilder().build(
        EconomicLedgerInput(
            source,
            (0.20,) * len(source.step_traces),
            (0.05,) * len(source.step_traces),
            0.85,
            model,
        )
    )
    intervals_csv_path = output_directory / "economic_ledger_intervals.csv"
    daily_csv_path = output_directory / "economic_ledger_daily_summary.csv"
    summary_path = output_directory / "economic_ledger_summary.txt"
    intervals_csv_path.write_text(_intervals_csv(ledger), encoding="utf-8", newline="")
    daily_csv_path.write_text(_daily_csv(ledger), encoding="utf-8", newline="")
    summary_path.write_text(_summary_text(ledger), encoding="utf-8", newline="")
    return EconomicLedgerReferenceResult(
        source,
        ledger,
        intervals_csv_path,
        daily_csv_path,
        summary_path,
    )


def _intervals_csv(ledger: DailyEconomicLedger) -> str:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        (
            "step_index",
            "timestamp",
            "duration_hours",
            "load_energy_kwh",
            "pv_energy_kwh",
            "grid_import_energy_kwh",
            "grid_export_energy_kwh",
            "battery_throughput_kwh",
            "soc_before_fraction",
            "soc_after_fraction",
            "import_tariff_per_kwh",
            "export_tariff_per_kwh",
            "degradation_cost_per_throughput_kwh",
            "realized_import_cost",
            "realized_export_revenue",
            "battery_degradation_cost",
            "realized_interval_net_cost",
            "cumulative_realized_net_cost",
        )
    )
    cumulative = 0.0
    for interval in ledger.intervals:
        cumulative += interval.realized_interval_net_cost
        writer.writerow(
            (
                interval.step_index,
                interval.timestamp.isoformat(),
                *(
                    _number(value)
                    for value in (
                        interval.duration_hours,
                        interval.load_energy_kwh,
                        interval.pv_energy_kwh,
                        interval.grid_import_energy_kwh,
                        interval.grid_export_energy_kwh,
                        interval.battery_throughput_kwh,
                        interval.soc_before_fraction,
                        interval.soc_after_fraction,
                        interval.import_tariff_per_kwh,
                        interval.export_tariff_per_kwh,
                        interval.degradation_cost_per_throughput_kwh,
                        interval.realized_import_cost,
                        interval.realized_export_revenue,
                        interval.battery_degradation_cost,
                        interval.realized_interval_net_cost,
                        cumulative,
                    )
                ),
            )
        )
    return stream.getvalue()


def _daily_csv(ledger: DailyEconomicLedger) -> str:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    fields = (
        "total_load_energy_kwh",
        "total_pv_energy_kwh",
        "total_grid_import_energy_kwh",
        "total_grid_export_energy_kwh",
        "total_battery_throughput_kwh",
        "total_realized_import_cost",
        "total_realized_export_revenue",
        "total_battery_degradation_cost",
        "total_realized_net_cost",
        "final_soc_fraction",
        "deliverable_terminal_energy_kwh",
        "terminal_valuation_price",
        "terminal_energy_value",
        "adjusted_net_economic_cost",
    )
    writer.writerow(fields)
    writer.writerow(
        _number(value)
        for value in (
            ledger.total_load_energy_kwh,
            ledger.total_pv_energy_kwh,
            ledger.total_grid_import_energy_kwh,
            ledger.total_grid_export_energy_kwh,
            ledger.total_battery_throughput_kwh,
            ledger.total_realized_import_cost,
            ledger.total_realized_export_revenue,
            ledger.total_battery_degradation_cost,
            ledger.total_realized_net_cost,
            ledger.final_soc_fraction,
            ledger.terminal_energy_value_evidence.deliverable_terminal_energy_kwh,
            ledger.terminal_energy_value_evidence.valuation_import_price,
            ledger.terminal_energy_value,
            ledger.adjusted_net_economic_cost,
        )
    )
    return stream.getvalue()


def _summary_text(ledger: DailyEconomicLedger) -> str:
    return (
        "EOS Daily / Interval Economic Ledger\n"
        "grid_sign=positive grid power is import; negative grid power is export.\n"
        "battery_throughput=sum(abs(actual battery power) * duration_hours).\n"
        f"energy: load={_number(ledger.total_load_energy_kwh)} pv={_number(ledger.total_pv_energy_kwh)} import={_number(ledger.total_grid_import_energy_kwh)} export={_number(ledger.total_grid_export_energy_kwh)} throughput={_number(ledger.total_battery_throughput_kwh)} final_soc={_number(ledger.final_soc_fraction)}\n"
        f"economics: import_cost={_number(ledger.total_realized_import_cost)} export_revenue={_number(ledger.total_realized_export_revenue)} degradation_cost={_number(ledger.total_battery_degradation_cost)} realized_net_cost={_number(ledger.total_realized_net_cost)} terminal_value={_number(ledger.terminal_energy_value)} adjusted_net_economic_cost={_number(ledger.adjusted_net_economic_cost)}\n"
        "Terminal value is one horizon-end credit and is not allocated across normal intervals. Negative adjusted net economic cost does not necessarily mean realized cash profit.\n"
    )


def _number(value: float) -> str:
    return f"{value:.6f}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EOS TASK-173 economic ledger")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("simulation_output_task173_economic_ledger"),
    )
    arguments = parser.parse_args(argv)
    result = run_reference_ledger(arguments.output_dir)
    for path in (
        result.intervals_csv_path,
        result.daily_csv_path,
        result.summary_path,
    ):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
