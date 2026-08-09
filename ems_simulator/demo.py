"""Runnable EOS EMS Simulator 1.0 household demonstration."""

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ems_simulator.input import BatteryParameters, DailySimulationScenarioInput
from ems_simulator.output import (
    DailySimulationExport,
    SimulationExportPaths,
    SimulationResultExporter,
)
from ems_simulator.runner import DailySimulationResult, DailySimulationRunner
from simulator import SimulationStepIdentity

PV_PROFILE_KW = (
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.2,
    1.0,
    2.5,
    4.0,
    5.0,
    5.5,
    5.8,
    5.4,
    4.5,
    3.2,
    1.8,
    0.6,
    0.1,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
)

LOAD_PROFILE_KW = (
    0.7,
    0.6,
    0.6,
    0.6,
    0.7,
    0.9,
    1.4,
    1.8,
    1.3,
    1.0,
    0.9,
    0.8,
    0.8,
    0.8,
    0.9,
    1.0,
    1.2,
    1.8,
    2.5,
    2.8,
    2.4,
    1.8,
    1.2,
    0.9,
)

TARIFF_PROFILE_CNY_PER_KWH = (
    0.30,
    0.30,
    0.30,
    0.30,
    0.30,
    0.30,
    0.55,
    0.55,
    0.55,
    0.55,
    0.55,
    0.55,
    0.55,
    0.55,
    0.55,
    0.55,
    0.90,
    0.90,
    0.90,
    0.90,
    0.90,
    0.90,
    0.55,
    0.55,
)


@dataclass(frozen=True, slots=True)
class DemoExecutionResult:
    """Preserve exact artifacts produced by one completed Demo execution."""

    source_input: DailySimulationScenarioInput
    simulation_result: DailySimulationResult
    export: DailySimulationExport
    paths: SimulationExportPaths
    summary_path: Path

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, DailySimulationScenarioInput):
            raise TypeError("source_input must be a DailySimulationScenarioInput")
        if not isinstance(self.simulation_result, DailySimulationResult):
            raise TypeError("simulation_result must be a DailySimulationResult")
        if not isinstance(self.export, DailySimulationExport):
            raise TypeError("export must be a DailySimulationExport")
        if not isinstance(self.paths, SimulationExportPaths):
            raise TypeError("paths must be SimulationExportPaths")
        if not isinstance(self.summary_path, Path):
            raise TypeError("summary_path must be a pathlib.Path")
        if self.simulation_result.source_input is not self.source_input:
            raise ValueError("simulation_result must preserve the exact source_input")
        if self.export.source_result is not self.simulation_result:
            raise ValueError("export must preserve the exact simulation_result")


def create_demo_scenario() -> DailySimulationScenarioInput:
    """Return the deterministic caller-owned household scenario."""
    start = datetime(2026, 1, 1, tzinfo=UTC)
    step_identities = tuple(
        SimulationStepIdentity(
            sequence=hour,
            duration_seconds=3600.0,
            timestamp=start + timedelta(hours=hour),
        )
        for hour in range(24)
    )
    battery_parameters = BatteryParameters(
        capacity_kwh=10.0,
        max_charge_power_kw=3.0,
        max_discharge_power_kw=3.0,
        charge_efficiency=0.95,
        discharge_efficiency=0.95,
        reserve_soc=0.20,
    )
    return DailySimulationScenarioInput(
        step_identities=step_identities,
        pv_power_curve_kw=PV_PROFILE_KW,
        load_power_curve_kw=LOAD_PROFILE_KW,
        tariff_curve_cny_per_kwh=TARIFF_PROFILE_CNY_PER_KWH,
        battery_parameters=battery_parameters,
        initial_soc=0.50,
    )


def run_demo(output_directory: Path) -> DemoExecutionResult:
    """Run the deterministic Demo once and write its engineering outputs."""
    if not isinstance(output_directory, Path):
        raise TypeError("output_directory must be a pathlib.Path")
    output_directory.mkdir(parents=True, exist_ok=True)

    source_input = create_demo_scenario()
    simulation_result = DailySimulationRunner.run(source_input)
    export = SimulationResultExporter.export(simulation_result)
    paths = SimulationResultExporter.write_files(export, output_directory)
    summary_path = output_directory / "daily_summary.txt"
    summary_path.write_text(
        _summary_text(export),
        encoding="utf-8",
        newline="",
    )
    return DemoExecutionResult(
        source_input,
        simulation_result,
        export,
        paths,
        summary_path,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line Demo and report its deterministic outputs."""
    parser = argparse.ArgumentParser(description="EOS EMS Simulator 1.0 Demo")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("simulation_output"),
        help="directory for CSV, SVG, and summary outputs",
    )
    arguments = parser.parse_args(argv)
    execution = run_demo(arguments.output_dir)
    print(f"CSV: {execution.paths.csv_path}")
    print(f"Power curve: {execution.paths.power_curve_path}")
    print(f"SOC curve: {execution.paths.soc_curve_path}")
    print(f"Daily summary: {execution.summary_path}")
    return 0


def _summary_text(export: DailySimulationExport) -> str:
    summary = export.summary
    return (
        "EOS EMS Simulator 1.0 Daily Summary\n"
        f"pv_energy_kwh={summary.pv_energy_kwh:.6f}\n"
        f"load_energy_kwh={summary.load_energy_kwh:.6f}\n"
        f"battery_throughput_kwh={summary.battery_throughput_kwh:.6f}\n"
        f"grid_import_energy_kwh={summary.grid_import_energy_kwh:.6f}\n"
        f"grid_export_energy_kwh={summary.grid_export_energy_kwh:.6f}\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
