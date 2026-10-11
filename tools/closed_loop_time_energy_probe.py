"""Test-only SOC-feedback probe independent of the legacy daily runner."""

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

from ems_simulator.demo import create_demo_scenario
from ems_simulator.input import BatteryParameters
from ems_simulator.time_energy import (
    PowerInterval,
    SimulationCadences,
    TimeEnergyInput,
    simulate_time_energy,
)

DAY_SECONDS = 86400
HOUR_SECONDS = 3600


@dataclass(frozen=True, slots=True)
class ExternalSegment:
    start_seconds: int
    end_seconds: int
    load_power_kw: float
    pv_power_kw: float


@dataclass(frozen=True, slots=True)
class ProbeCase:
    name: str
    initial_soc: float
    battery_parameters: BatteryParameters
    external_segments: tuple[ExternalSegment, ...]


@dataclass(frozen=True, slots=True)
class ControlDecision:
    time_seconds: int
    feedback_soc: float
    load_power_kw: float
    pv_power_kw: float
    request_power_kw: float


@dataclass(frozen=True, slots=True)
class DeliveredSlice:
    start_seconds: float
    end_seconds: float
    load_power_kw: float
    pv_power_kw: float
    request_power_kw: float
    actual_power_kw: float
    grid_power_kw: float
    soc_before: float
    soc_after: float


@dataclass(frozen=True, slots=True)
class ProbeResult:
    case: ProbeCase
    physical_step_seconds: float
    control_period_seconds: int
    record_seconds: float
    display_seconds: float
    decisions: tuple[ControlDecision, ...]
    slices: tuple[DeliveredSlice, ...]
    final_soc: float
    load_energy_kwh: float
    pv_energy_kwh: float
    battery_delivered_energy_kwh: float
    grid_import_energy_kwh: float
    grid_export_energy_kwh: float


def _hourly_segments(
    load: tuple[float, ...], pv: tuple[float, ...]
) -> tuple[ExternalSegment, ...]:
    return tuple(
        ExternalSegment(
            hour * HOUR_SECONDS, (hour + 1) * HOUR_SECONDS, load[hour], pv[hour]
        )
        for hour in range(24)
    )


def cases() -> dict[str, ProbeCase]:
    demo = create_demo_scenario()
    parameters = demo.battery_parameters
    return {
        "normal_day": ProbeCase(
            "normal_day",
            demo.initial_soc,
            parameters,
            _hourly_segments(demo.load_power_curve_kw, demo.pv_power_curve_kw),
        ),
        "upper_bound": ProbeCase(
            "upper_bound",
            0.98,
            parameters,
            (
                ExternalSegment(0, 3600, 1.0, 5.0),
                ExternalSegment(3600, 7200, 1.0, 5.0),
                ExternalSegment(7200, DAY_SECONDS, 0.0, 0.0),
            ),
        ),
        "lower_bound": ProbeCase(
            "lower_bound",
            0.21,
            parameters,
            (
                ExternalSegment(0, 3600, 3.0, 0.0),
                ExternalSegment(3600, 7200, 3.0, 0.0),
                ExternalSegment(7200, DAY_SECONDS, 0.0, 0.0),
            ),
        ),
        "flow_reversal": ProbeCase(
            "flow_reversal",
            parameters.reserve_soc,
            parameters,
            (
                ExternalSegment(0, 1800, 2.0, 0.0),
                ExternalSegment(1800, 3600, 1.0, 3.0),
                ExternalSegment(3600, 7200, 1.0, 3.0),
                ExternalSegment(7200, DAY_SECONDS, 0.0, 0.0),
            ),
        ),
    }


def _external_at(case: ProbeCase, time_seconds: float) -> ExternalSegment:
    for segment in case.external_segments:
        if segment.start_seconds <= time_seconds < segment.end_seconds:
            return segment
    raise ValueError(f"external input is absent at {time_seconds}")


def _request(load_kw: float, pv_kw: float, soc: float, reserve: float) -> float:
    """Mirror the Demo's imbalance/reserve policy, not its physics or state."""
    imbalance_kw = pv_kw - load_kw
    return imbalance_kw if imbalance_kw >= 0 or soc > reserve else 0.0


def run_probe(
    case: ProbeCase,
    *,
    physical_step_seconds: float,
    control_period_seconds: int = HOUR_SECONDS,
    record_seconds: float = 60.0,
    display_seconds: float = 5.0,
) -> ProbeResult:
    """Decide only at scheduled control times; integrate event-split physics."""
    if DAY_SECONDS % control_period_seconds:
        raise ValueError("control period must divide the simulated day")
    expected_start = 0
    for segment in case.external_segments:
        if segment.start_seconds != expected_start:
            raise ValueError("external segments must be ordered and contiguous")
        expected_start = segment.end_seconds
    if expected_start != DAY_SECONDS:
        raise ValueError("external segments must cover exactly one day")

    decisions: list[ControlDecision] = []
    slices: list[DeliveredSlice] = []
    soc = case.initial_soc
    load_energy = pv_energy = battery_energy = import_energy = export_energy = 0.0
    for tick in range(0, DAY_SECONDS, control_period_seconds):
        external = _external_at(case, tick)
        request = _request(
            external.load_power_kw,
            external.pv_power_kw,
            soc,
            case.battery_parameters.reserve_soc,
        )
        decisions.append(
            ControlDecision(
                tick, soc, external.load_power_kw, external.pv_power_kw, request
            )
        )
        control_end = tick + control_period_seconds
        intervals = tuple(
            PowerInterval(
                max(segment.start_seconds, tick) - tick,
                min(segment.end_seconds, control_end) - tick,
                segment.load_power_kw,
                segment.pv_power_kw,
                request,
            )
            for segment in case.external_segments
            if segment.start_seconds < control_end and segment.end_seconds > tick
        )
        result = simulate_time_energy(
            TimeEnergyInput(
                SimulationCadences(
                    physical_step_seconds,
                    float(control_period_seconds),
                    3600.0,
                    record_seconds,
                    display_seconds,
                ),
                intervals,
                case.battery_parameters,
                soc,
            )
        )
        for item in result.slices:
            absolute_start = tick + item.start_seconds
            external = _external_at(case, absolute_start)
            slices.append(
                DeliveredSlice(
                    absolute_start,
                    tick + item.end_seconds,
                    external.load_power_kw,
                    external.pv_power_kw,
                    item.requested_battery_power_kw,
                    item.actual_battery_power_kw,
                    item.grid_power_kw,
                    item.soc_before,
                    item.soc_after,
                )
            )
        soc = result.final_soc
        load_energy += result.load_energy_kwh
        pv_energy += result.pv_energy_kwh
        battery_energy += result.battery_delivered_energy_kwh
        import_energy += result.grid_import_energy_kwh
        export_energy += result.grid_export_energy_kwh
    return ProbeResult(
        case,
        physical_step_seconds,
        control_period_seconds,
        record_seconds,
        display_seconds,
        tuple(decisions),
        tuple(slices),
        soc,
        load_energy,
        pv_energy,
        battery_energy,
        import_energy,
        export_energy,
    )


def hourly_rows(result: ProbeResult) -> list[dict[str, int | float]]:
    rows: list[dict[str, int | float]] = []
    for hour in range(24):
        start, end = hour * HOUR_SECONDS, (hour + 1) * HOUR_SECONDS
        slices = [item for item in result.slices if start <= item.start_seconds < end]
        if not slices or slices[-1].end_seconds != end:
            raise AssertionError(f"hour {hour} is not fully covered")
        hours = [
            (item.end_seconds - item.start_seconds) / HOUR_SECONDS for item in slices
        ]
        rows.append(
            {
                "hour": hour,
                "soc_end": slices[-1].soc_after,
                "average_actual_kw": sum(
                    item.actual_power_kw * duration
                    for item, duration in zip(slices, hours, strict=True)
                ),
                "charge_kwh": sum(
                    max(item.actual_power_kw, 0.0) * duration
                    for item, duration in zip(slices, hours, strict=True)
                ),
                "discharge_kwh": sum(
                    max(-item.actual_power_kw, 0.0) * duration
                    for item, duration in zip(slices, hours, strict=True)
                ),
                "import_kwh": sum(
                    max(item.grid_power_kw, 0.0) * duration
                    for item, duration in zip(slices, hours, strict=True)
                ),
                "export_kwh": sum(
                    max(-item.grid_power_kw, 0.0) * duration
                    for item, duration in zip(slices, hours, strict=True)
                ),
            }
        )
    return rows


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    arguments.output_dir.mkdir(parents=True, exist_ok=False)

    results = [
        run_probe(case, physical_step_seconds=step)
        for case in cases().values()
        for step in (3600.0, 60.0, 15.0)
    ]
    results.append(
        run_probe(
            cases()["flow_reversal"],
            physical_step_seconds=60.0,
            control_period_seconds=1800,
        )
    )
    summaries: list[dict[str, object]] = []
    hourly: list[dict[str, object]] = []
    decisions: list[dict[str, object]] = []
    event_window: list[dict[str, object]] = []
    for result in results:
        key = {
            "case": result.case.name,
            "physical_step_seconds": result.physical_step_seconds,
            "control_period_seconds": result.control_period_seconds,
        }
        summaries.append(
            {
                **key,
                "decisions": len(result.decisions),
                "final_soc": result.final_soc,
                "load_kwh": result.load_energy_kwh,
                "pv_kwh": result.pv_energy_kwh,
                "battery_signed_kwh": result.battery_delivered_energy_kwh,
                "import_kwh": result.grid_import_energy_kwh,
                "export_kwh": result.grid_export_energy_kwh,
            }
        )
        hourly.extend({**key, **row} for row in hourly_rows(result))
        decisions.extend(
            {
                **key,
                "time_seconds": item.time_seconds,
                "feedback_soc": item.feedback_soc,
                "load_kw": item.load_power_kw,
                "pv_kw": item.pv_power_kw,
                "request_kw": item.request_power_kw,
            }
            for item in result.decisions
        )
        if result.case.name == "flow_reversal":
            event_window.extend(
                {
                    **key,
                    "start_seconds": item.start_seconds,
                    "end_seconds": item.end_seconds,
                    "load_kw": item.load_power_kw,
                    "pv_kw": item.pv_power_kw,
                    "request_kw": item.request_power_kw,
                    "actual_kw": item.actual_power_kw,
                    "grid_kw": item.grid_power_kw,
                }
                for item in result.slices
                if item.start_seconds < HOUR_SECONDS
            )
    for name, rows in (
        ("summary.csv", summaries),
        ("hourly.csv", hourly),
        ("decisions.csv", decisions),
        ("event_window.csv", event_window),
    ):
        _write_csv(arguments.output_dir / name, rows)
    for row in summaries:
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
