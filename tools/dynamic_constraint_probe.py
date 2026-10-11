"""Independent, test-only scheduled-control audit over new time-energy physics."""

import argparse
import csv
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from ems_simulator.input import BatteryParameters
from ems_simulator.time_energy import (
    PowerInterval,
    SimulationCadences,
    TimeEnergyInput,
    simulate_time_energy,
)

DURATION_SECONDS = 7200
HOUR_SECONDS = 3600


@dataclass(frozen=True, slots=True)
class FactSegment:
    start: int
    end: int
    load_kw: float
    pv_kw: float
    grid_charge_allowed: bool
    zero_export: bool
    reserve_target_soc: float


@dataclass(frozen=True, slots=True)
class Case:
    name: str
    initial_soc: float
    segments: tuple[FactSegment, ...]


@dataclass(frozen=True, slots=True)
class Decision:
    time: int
    feedback_soc: float
    request_kw: float


@dataclass(frozen=True, slots=True)
class LedgerRow:
    case: str
    start: float
    end: float
    load_kw: float
    pv_kw: float
    request_kw: float
    actual_kw: float
    grid_kw: float
    soc_before: float
    soc_after: float
    grid_charge_allowed: bool
    zero_export: bool
    reserve_target_soc: float
    load_kwh: float
    pv_kwh: float
    battery_kwh: float
    import_kwh: float
    export_kwh: float
    grid_to_battery_kwh: float
    prohibited_grid_charge_kwh: float
    zero_export_violation_kwh: float
    curtailment_kwh: float
    unserved_load_kwh: float
    storage_delta_kwh: float
    conversion_loss_kwh: float
    target_gap_kwh_end: float


@dataclass(frozen=True, slots=True)
class ProbeResult:
    case: Case
    physical_step: float
    control_period: int
    record_period: float
    display_period: float
    decisions: tuple[Decision, ...]
    ledger: tuple[LedgerRow, ...]
    final_soc: float
    export_peak_kw: float
    export_duration_s: float
    export_violation_kwh: float
    prohibited_grid_charge_kwh: float


def battery() -> BatteryParameters:
    return BatteryParameters(10.0, 3.0, 3.0, 0.95, 0.95, 0.2)


def cases() -> dict[str, Case]:
    def segment(
        start: int,
        end: int,
        load: float,
        pv: float,
        allowed: bool,
        zero: bool,
        target: float,
    ) -> FactSegment:
        return FactSegment(start, end, load, pv, allowed, zero, target)

    return {
        "steady_zero_export": Case(
            "steady_zero_export", 0.5, (segment(0, 7200, 1, 2, False, True, 0.2),)
        ),
        "pv_jump": Case(
            "pv_jump",
            0.5,
            (
                segment(0, 1800, 2, 0, False, True, 0.2),
                segment(1800, 7200, 2, 5, False, True, 0.2),
            ),
        ),
        "load_drop": Case(
            "load_drop",
            0.5,
            (
                segment(0, 1800, 3, 3, False, True, 0.2),
                segment(1800, 7200, 0, 3, False, True, 0.2),
            ),
        ),
        "full_battery": Case(
            "full_battery", 1.0, (segment(0, 7200, 1, 5, False, True, 0.2),)
        ),
        "soc_floor": Case(
            "soc_floor", 0.21, (segment(0, 7200, 3, 0, False, True, 0.2),)
        ),
        "permission_mid_tick": Case(
            "permission_mid_tick",
            0.3,
            (
                segment(0, 1800, 1, 0, True, False, 0.8),
                segment(1800, 7200, 1, 0, False, False, 0.8),
            ),
        ),
        "permission_on_tick": Case(
            "permission_on_tick",
            0.3,
            (
                segment(0, 3600, 1, 0, True, False, 0.8),
                segment(3600, 7200, 1, 0, False, False, 0.8),
            ),
        ),
        "target_switch": Case(
            "target_switch",
            0.5,
            (
                segment(0, 1800, 1, 0, True, False, 0.2),
                segment(1800, 7200, 1, 0, True, False, 0.8),
            ),
        ),
        "simultaneous": Case(
            "simultaneous",
            0.5,
            (
                segment(0, 1800, 1, 0, True, False, 0.8),
                segment(1800, 7200, 0, 5, False, True, 0.9),
            ),
        ),
    }


def _fact_at(case: Case, time: float) -> FactSegment:
    for fact in case.segments:
        if fact.start <= time < fact.end:
            return fact
    raise ValueError(f"missing external facts at {time}")


def _request(fact: FactSegment, soc: float, parameters: BatteryParameters) -> float:
    """Simple scheduled request, not a new optimizer or execution limiter."""
    surplus = fact.pv_kw - fact.load_kw
    if surplus > 0:
        return min(surplus, parameters.max_charge_power_kw)
    if soc < fact.reserve_target_soc and fact.grid_charge_allowed:
        return parameters.max_charge_power_kw
    if soc > fact.reserve_target_soc and surplus < 0:
        return -min(-surplus, parameters.max_discharge_power_kw)
    return 0.0


def run_probe(
    case: Case,
    *,
    physical_step: float,
    control_period: int = HOUR_SECONDS,
    record_period: float = 60.0,
    display_period: float = 5.0,
) -> ProbeResult:
    if DURATION_SECONDS % control_period:
        raise ValueError("control period must divide duration")
    expected = 0
    for fact in case.segments:
        if fact.start != expected or fact.end <= fact.start:
            raise ValueError("facts must be contiguous and advancing")
        if not 0 <= fact.reserve_target_soc <= 1:
            raise ValueError("reserve target must be a fraction")
        expected = fact.end
    if expected != DURATION_SECONDS:
        raise ValueError("facts must cover the entire run")

    parameters = battery()
    soc = case.initial_soc
    decisions: list[Decision] = []
    ledger: list[LedgerRow] = []
    for tick in range(0, DURATION_SECONDS, control_period):
        fact = _fact_at(case, tick)
        request = _request(fact, soc, parameters)
        decisions.append(Decision(tick, soc, request))
        tick_end = tick + control_period
        intervals = tuple(
            PowerInterval(
                max(item.start, tick) - tick,
                min(item.end, tick_end) - tick,
                item.load_kw,
                item.pv_kw,
                request,
            )
            for item in case.segments
            if item.start < tick_end and item.end > tick
        )
        result = simulate_time_energy(
            TimeEnergyInput(
                SimulationCadences(
                    physical_step,
                    float(control_period),
                    3600.0,
                    record_period,
                    display_period,
                ),
                intervals,
                parameters,
                soc,
            )
        )
        for item in result.slices:
            start = tick + item.start_seconds
            end = tick + item.end_seconds
            current = _fact_at(case, start)
            hours = (end - start) / HOUR_SECONDS
            actual = item.actual_battery_power_kw
            grid = item.grid_power_kw
            grid_charge_kw = (
                max(0.0, actual - max(current.pv_kw - current.load_kw, 0.0))
                if actual > 0
                else 0.0
            )
            battery_kwh = actual * hours
            storage_delta = (item.soc_after - item.soc_before) * parameters.capacity_kwh
            conversion_loss = (
                battery_kwh - storage_delta
                if actual > 0
                else battery_kwh - storage_delta
                if actual < 0
                else 0.0
            )
            ledger.append(
                LedgerRow(
                    case.name,
                    start,
                    end,
                    current.load_kw,
                    current.pv_kw,
                    item.requested_battery_power_kw,
                    actual,
                    grid,
                    item.soc_before,
                    item.soc_after,
                    current.grid_charge_allowed,
                    current.zero_export,
                    current.reserve_target_soc,
                    current.load_kw * hours,
                    current.pv_kw * hours,
                    battery_kwh,
                    max(grid, 0.0) * hours,
                    max(-grid, 0.0) * hours,
                    grid_charge_kw * hours,
                    grid_charge_kw * hours if not current.grid_charge_allowed else 0.0,
                    max(-grid, 0.0) * hours if current.zero_export else 0.0,
                    0.0,
                    0.0,
                    storage_delta,
                    conversion_loss,
                    max(0.0, current.reserve_target_soc - item.soc_after)
                    * parameters.capacity_kwh,
                )
            )
        soc = result.final_soc

    return ProbeResult(
        case,
        physical_step,
        control_period,
        record_period,
        display_period,
        tuple(decisions),
        tuple(ledger),
        soc,
        max(
            (max(-item.grid_kw, 0.0) for item in ledger if item.zero_export),
            default=0.0,
        ),
        sum(
            item.end - item.start
            for item in ledger
            if item.zero_export and item.grid_kw < -1e-10
        ),
        sum(item.zero_export_violation_kwh for item in ledger),
        sum(item.prohibited_grid_charge_kwh for item in ledger),
    )


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _zero_export_assessment(result: ProbeResult) -> tuple[str, str]:
    enabled = [row for row in result.ledger if row.zero_export]
    if not enabled:
        return "NOT_APPLICABLE", "NOT_ENABLED"
    if result.export_violation_kwh <= 8e-11:
        return "PASS", "NONE"
    reasons: set[str] = set()
    for row in enabled:
        if row.grid_kw >= -1e-10:
            continue
        if row.soc_before >= 1 - 1e-9 and row.actual_kw == 0:
            reasons.add("FULL_SOC_NO_CURTAILMENT")
        elif row.pv_kw - row.load_kw > 3 + 1e-10 and row.actual_kw >= 3 - 1e-10:
            reasons.add("CHARGE_LIMIT_NO_CURTAILMENT")
        else:
            reasons.add("HELD_REQUEST_AFTER_EVENT")
    status = (
        "FAIL_UNSUPPORTED"
        if any("NO_CURTAILMENT" in reason for reason in reasons)
        else "FAIL_CONTROL_DELAY"
    )
    return status, "|".join(sorted(reasons))


def _svg_curve(result: ProbeResult, path: Path) -> None:
    """Draw actual signed grid power and SOC versus simulation time."""
    width, height = 960, 430
    left, right, bottom = 80, 25, 50
    plot_width = width - left - right
    grid_top, grid_bottom = 75, 240
    soc_top, soc_bottom = 270, height - bottom
    peak = max(5.0, *(abs(item.grid_kw) for item in result.ledger))

    def x(seconds: float) -> float:
        return left + seconds / DURATION_SECONDS * plot_width

    def grid_y(kw: float) -> float:
        return (grid_top + grid_bottom) / 2 - kw / peak * (grid_bottom - grid_top) / 2

    def soc_y(soc: float) -> float:
        return soc_bottom - soc * (soc_bottom - soc_top)

    def stepped_points(attribute: str, mapper: Callable[[float], float]) -> str:
        points: list[str] = []
        for row in result.ledger:
            value = getattr(row, attribute)
            points.extend(
                (
                    f"{x(row.start):.2f},{mapper(value):.2f}",
                    f"{x(row.end):.2f},{mapper(value):.2f}",
                )
            )
        return " ".join(points)

    soc_points = " ".join(
        [f"{x(result.ledger[0].start):.2f},{soc_y(result.ledger[0].soc_before):.2f}"]
        + [f"{x(row.end):.2f},{soc_y(row.soc_after):.2f}" for row in result.ledger]
    )
    svg = ET.Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "width": str(width),
            "height": str(height),
            "viewBox": f"0 0 {width} {height}",
        },
    )
    ET.SubElement(svg, "rect", {"width": "100%", "height": "100%", "fill": "white"})

    def label(x_pos: float, y_pos: float, value: str, size: int = 13) -> None:
        node = ET.SubElement(
            svg,
            "text",
            {
                "x": str(x_pos),
                "y": str(y_pos),
                "font-family": "sans-serif",
                "font-size": str(size),
            },
        )
        node.text = value

    label(left, 25, f"{result.case.name}: actual grid kW and SOC (60 s)", 18)
    for fact in result.case.segments[1:]:
        ET.SubElement(
            svg,
            "line",
            {
                "x1": f"{x(fact.start):.2f}",
                "x2": f"{x(fact.start):.2f}",
                "y1": str(grid_top),
                "y2": str(soc_bottom),
                "stroke": "#aaa",
                "stroke-dasharray": "4 4",
            },
        )
    ET.SubElement(
        svg,
        "line",
        {
            "x1": str(left),
            "x2": str(width - right),
            "y1": f"{grid_y(0):.2f}",
            "y2": f"{grid_y(0):.2f}",
            "stroke": "#777",
        },
    )
    for points, color in (
        (stepped_points("grid_kw", grid_y), "#c23b32"),
        (soc_points, "#2766a8"),
    ):
        ET.SubElement(
            svg,
            "polyline",
            {
                "points": points,
                "fill": "none",
                "stroke": color,
                "stroke-width": "2",
            },
        )
    label(8, grid_top, "grid +import")
    label(8, grid_bottom, "-export")
    label(8, soc_top, "SOC")
    label(left, height - 14, "0 s")
    label(width - right - 48, height - 14, "7200 s")
    ET.ElementTree(svg).write(path, encoding="utf-8", xml_declaration=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    arguments.output_dir.mkdir(parents=True, exist_ok=False)

    results = [
        run_probe(case, physical_step=step)
        for case in cases().values()
        for step in (3600.0, 60.0, 15.0)
    ]
    summaries: list[dict[str, object]] = []
    decisions: list[dict[str, object]] = []
    ledger: list[dict[str, object]] = []
    for result in results:
        export_status, export_reason = _zero_export_assessment(result)
        key: dict[str, object] = {
            "case": result.case.name,
            "step_s": result.physical_step,
            "control_s": result.control_period,
        }
        summaries.append(
            {
                **key,
                "decisions": len(result.decisions),
                "final_soc": result.final_soc,
                "import_kwh": sum(row.import_kwh for row in result.ledger),
                "export_kwh": sum(row.export_kwh for row in result.ledger),
                "zero_export_peak_kw": result.export_peak_kw,
                "zero_export_duration_s": result.export_duration_s,
                "zero_export_violation_kwh": result.export_violation_kwh,
                "prohibited_grid_charge_kwh": result.prohibited_grid_charge_kwh,
                "curtailment_kwh": 0.0,
                "unserved_load_kwh": 0.0,
                "target_gap_kwh_end": result.ledger[-1].target_gap_kwh_end,
                "zero_export_status": export_status,
                "zero_export_reason": export_reason,
                "grid_charge_status": "NOT_APPLICABLE"
                if all(row.grid_charge_allowed for row in result.ledger)
                else "FAIL"
                if result.prohibited_grid_charge_kwh > 8e-11
                else "PASS",
            }
        )
        decisions.extend(
            {
                **key,
                "time_s": decision.time,
                "feedback_soc": decision.feedback_soc,
                "request_kw": decision.request_kw,
            }
            for decision in result.decisions
        )
        ledger.extend({**key, **asdict(row)} for row in result.ledger)
        if result.physical_step == 60.0:
            _svg_curve(result, arguments.output_dir / f"{result.case.name}_curve.svg")
    _write_csv(arguments.output_dir / "summary.csv", summaries)
    _write_csv(arguments.output_dir / "decisions.csv", decisions)
    _write_csv(arguments.output_dir / "ledger.csv", ledger)
    for summary in summaries:
        print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
