"""Deterministic engineering outputs for completed daily simulations."""

import csv
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

from ems_simulator.runner import DailySimulationResult
from simulator.validation import require_non_negative_number

CSV_HEADER = (
    "timestamp",
    "pv_power_kw",
    "load_power_kw",
    "battery_power_kw",
    "grid_power_kw",
    "soc",
)


@dataclass(frozen=True, slots=True)
class DailyEnergySummary:
    """Preserve deterministic daily energy totals derived from one result.

    All values are finite non-negative raw kWh. Battery throughput is the sum
    of absolute realized Battery energy. Grid import and export are reported as
    separate positive magnitudes.
    """

    source_result: DailySimulationResult
    pv_energy_kwh: float
    load_energy_kwh: float
    battery_throughput_kwh: float
    grid_import_energy_kwh: float
    grid_export_energy_kwh: float

    def __post_init__(self) -> None:
        if not isinstance(self.source_result, DailySimulationResult):
            raise TypeError("source_result must be a DailySimulationResult")
        for field_name in (
            "pv_energy_kwh",
            "load_energy_kwh",
            "battery_throughput_kwh",
            "grid_import_energy_kwh",
            "grid_export_energy_kwh",
        ):
            object.__setattr__(
                self,
                field_name,
                require_non_negative_number(getattr(self, field_name), field_name),
            )


@dataclass(frozen=True, slots=True)
class SimulationVisualization:
    """Hold deterministic SVG renderings for exact simulation evidence."""

    source_result: DailySimulationResult
    power_curve_svg: str
    soc_curve_svg: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_result, DailySimulationResult):
            raise TypeError("source_result must be a DailySimulationResult")
        if not isinstance(self.power_curve_svg, str):
            raise TypeError("power_curve_svg must be a str")
        if not isinstance(self.soc_curve_svg, str):
            raise TypeError("soc_curve_svg must be a str")


@dataclass(frozen=True, slots=True)
class DailySimulationExport:
    """Aggregate immutable CSV, summary, and visualization outputs."""

    source_result: DailySimulationResult
    csv_content: str
    summary: DailyEnergySummary
    visualization: SimulationVisualization

    def __post_init__(self) -> None:
        if not isinstance(self.source_result, DailySimulationResult):
            raise TypeError("source_result must be a DailySimulationResult")
        if not isinstance(self.csv_content, str):
            raise TypeError("csv_content must be a str")
        if not isinstance(self.summary, DailyEnergySummary):
            raise TypeError("summary must be a DailyEnergySummary")
        if not isinstance(self.visualization, SimulationVisualization):
            raise TypeError("visualization must be a SimulationVisualization")
        if self.summary.source_result is not self.source_result:
            raise ValueError("summary must preserve the exact source_result")
        if self.visualization.source_result is not self.source_result:
            raise ValueError("visualization must preserve the exact source_result")


@dataclass(frozen=True, slots=True)
class SimulationExportPaths:
    """Report exact caller-targeted files written by the export layer."""

    csv_path: Path
    power_curve_path: Path
    soc_curve_path: Path

    def __post_init__(self) -> None:
        for field_name in ("csv_path", "power_curve_path", "soc_curve_path"):
            if not isinstance(getattr(self, field_name), Path):
                raise TypeError(f"{field_name} must be a pathlib.Path")


class SimulationResultExporter:
    """Read a completed result and create deterministic engineering outputs."""

    __slots__ = ()

    @staticmethod
    def export(result: DailySimulationResult) -> DailySimulationExport:
        """Return immutable output artifacts without modifying the result."""
        SimulationResultExporter._require_result(result)
        summary = SimulationResultExporter._summarize(result)
        visualization = SimulationResultExporter._visualize(result)
        return DailySimulationExport(
            result,
            SimulationResultExporter._to_csv(result),
            summary,
            visualization,
        )

    @staticmethod
    def write_files(
        export: DailySimulationExport,
        output_directory: Path,
    ) -> SimulationExportPaths:
        """Write deterministic CSV and SVG files to an existing directory."""
        if not isinstance(export, DailySimulationExport):
            raise TypeError("export must be a DailySimulationExport")
        if not isinstance(output_directory, Path):
            raise TypeError("output_directory must be a pathlib.Path")
        if not output_directory.is_dir():
            raise ValueError("output_directory must be an existing directory")

        paths = SimulationExportPaths(
            output_directory / "simulation_result.csv",
            output_directory / "power_curve.svg",
            output_directory / "soc_curve.svg",
        )
        paths.csv_path.write_text(export.csv_content, encoding="utf-8", newline="")
        paths.power_curve_path.write_text(
            export.visualization.power_curve_svg,
            encoding="utf-8",
            newline="",
        )
        paths.soc_curve_path.write_text(
            export.visualization.soc_curve_svg,
            encoding="utf-8",
            newline="",
        )
        return paths

    @staticmethod
    def _to_csv(result: DailySimulationResult) -> str:
        stream = StringIO(newline="")
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(CSV_HEADER)
        for trace in result.traces:
            timestamp = trace.simulation_input.step_identity.timestamp
            if timestamp is None:
                raise ValueError("every exported step must have an explicit timestamp")
            writer.writerow(
                (
                    timestamp.isoformat(),
                    trace.state.pv_result.actual_power_kw,
                    trace.state.load_result.actual_power_kw,
                    trace.state.battery_result.actual_power_kw,
                    trace.state.grid_result.actual_grid_power_kw,
                    trace.state.battery_result.next_state.soc,
                )
            )
        return stream.getvalue()

    @staticmethod
    def _summarize(result: DailySimulationResult) -> DailyEnergySummary:
        pv_energy_kwh = 0.0
        load_energy_kwh = 0.0
        battery_throughput_kwh = 0.0
        grid_import_energy_kwh = 0.0
        grid_export_energy_kwh = 0.0

        for trace in result.traces:
            duration_hours = (
                trace.simulation_input.step_identity.duration_seconds / 3600.0
            )
            pv_energy_kwh += trace.state.pv_result.actual_power_kw * duration_hours
            load_energy_kwh += trace.state.load_result.actual_power_kw * duration_hours
            battery_throughput_kwh += (
                abs(trace.state.battery_result.actual_power_kw) * duration_hours
            )
            grid_power_kw = trace.state.grid_result.actual_grid_power_kw
            if grid_power_kw >= 0:
                grid_import_energy_kwh += grid_power_kw * duration_hours
            else:
                grid_export_energy_kwh += -grid_power_kw * duration_hours

        return DailyEnergySummary(
            result,
            pv_energy_kwh,
            load_energy_kwh,
            battery_throughput_kwh,
            grid_import_energy_kwh,
            grid_export_energy_kwh,
        )

    @staticmethod
    def _visualize(result: DailySimulationResult) -> SimulationVisualization:
        pv = tuple(trace.state.pv_result.actual_power_kw for trace in result.traces)
        load = tuple(trace.state.load_result.actual_power_kw for trace in result.traces)
        battery = tuple(
            trace.state.battery_result.actual_power_kw for trace in result.traces
        )
        grid = tuple(
            trace.state.grid_result.actual_grid_power_kw for trace in result.traces
        )
        soc = tuple(
            trace.state.battery_result.next_state.soc for trace in result.traces
        )
        return SimulationVisualization(
            result,
            SimulationResultExporter._power_svg(pv, load, battery, grid),
            SimulationResultExporter._soc_svg(soc),
        )

    @staticmethod
    def _power_svg(
        pv: tuple[float, ...],
        load: tuple[float, ...],
        battery: tuple[float, ...],
        grid: tuple[float, ...],
    ) -> str:
        width, height = 960, 420
        left, right, top, bottom = 60.0, 930.0, 30.0, 370.0
        maximum = max(
            1.0,
            *(abs(value) for series in (pv, load, battery, grid) for value in series),
        )

        def point(index: int, value: float) -> str:
            x = left + (right - left) * index / (len(pv) - 1)
            y = top + (maximum - value) * (bottom - top) / (2.0 * maximum)
            return f"{x:.2f},{y:.2f}"

        series = (
            ("PV", "#f59e0b", pv),
            ("Load", "#2563eb", load),
            ("Battery", "#16a34a", battery),
            ("Grid", "#dc2626", grid),
        )
        polylines = "".join(
            f'<polyline data-series="{name}" fill="none" stroke="{color}" '
            f'stroke-width="2" points="'
            + " ".join(point(index, value) for index, value in enumerate(values))
            + '"/>'
            for name, color, values in series
        )
        zero_y = top + (bottom - top) / 2.0
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">'
            '<rect width="100%" height="100%" fill="white"/>'
            '<text x="60" y="20" font-family="sans-serif" font-size="16">'
            "Power curves (kW)</text>"
            f'<line x1="{left:.2f}" y1="{zero_y:.2f}" x2="{right:.2f}" '
            f'y2="{zero_y:.2f}" stroke="#64748b" stroke-width="1"/>'
            f"{polylines}</svg>\n"
        )

    @staticmethod
    def _soc_svg(soc: tuple[float, ...]) -> str:
        width, height = 960, 260
        left, right, top, bottom = 60.0, 930.0, 30.0, 220.0
        points = " ".join(
            f"{left + (right - left) * index / (len(soc) - 1):.2f},"
            f"{bottom - value * (bottom - top):.2f}"
            for index, value in enumerate(soc)
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">'
            '<rect width="100%" height="100%" fill="white"/>'
            '<text x="60" y="20" font-family="sans-serif" font-size="16">'
            "State of charge</text>"
            f'<line x1="{left:.2f}" y1="{bottom:.2f}" x2="{right:.2f}" '
            f'y2="{bottom:.2f}" stroke="#64748b" stroke-width="1"/>'
            '<polyline data-series="SOC" fill="none" stroke="#7c3aed" '
            f'stroke-width="2" points="{points}"/></svg>\n'
        )

    @staticmethod
    def _require_result(result: object) -> None:
        if not isinstance(result, DailySimulationResult):
            raise TypeError("result must be a DailySimulationResult")
