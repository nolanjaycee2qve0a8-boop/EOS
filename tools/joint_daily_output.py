"""Read-only aggregation of the single execution ledger; never simulates."""

import csv
import json
from dataclasses import asdict
from datetime import timedelta
from itertools import pairwise
from math import fsum, isfinite
from pathlib import Path
from xml.etree import ElementTree as ET

from tools.joint_execution_contract import (
    DAY_SECONDS,
    ENERGY_TOL,
    POWER_TOL,
    SOC_TOL,
    START_UTC,
    TIME_TOL,
)
from tools.pv_curtailment_probe import CurtailmentRow, physical_audit_rows
from tools.pv_grid_charge_joint_probe import JointResult, write_evidence

ENERGIES = (
    "available_pv_kwh",
    "delivered_pv_kwh",
    "curtailed_pv_kwh",
    "load_kwh",
    "battery_kwh",
    "import_kwh",
    "export_kwh",
    "grid_to_battery_kwh",
    "prohibited_grid_charge_kwh",
    "storage_delta_kwh",
    "conversion_loss_kwh",
)
POWERS = (
    "original_request_kw",
    "constrained_request_kw",
    "actual_battery_kw",
    "available_pv_kw",
    "delivered_pv_kw",
    "curtailed_pv_kw",
    "load_kw",
    "grid_kw",
)


def validate_ledger(rows: tuple[CurtailmentRow, ...]) -> None:
    if not rows or rows[0].start_s != 0 or rows[-1].end_s != DAY_SECONDS:
        raise ValueError("ledger must cover exactly one complete UTC day")
    end, soc = 0.0, rows[0].soc_before
    for row in rows:
        if abs(row.start_s - end) > TIME_TOL or row.end_s <= row.start_s:
            raise ValueError("ledger has a gap, overlap or duplicate")
        numbers = [getattr(row, key) for key in (*ENERGIES, *POWERS)]
        if not all(isfinite(value) for value in numbers):
            raise ValueError("nonfinite ledger")
        if abs(row.soc_before - soc) > SOC_TOL:
            raise ValueError("discontinuous SOC")
        hours = (row.end_s - row.start_s) / 3600
        residuals = (
            row.available_pv_kwh - row.delivered_pv_kwh - row.curtailed_pv_kwh,
            row.load_kwh
            + row.battery_kwh
            - row.delivered_pv_kwh
            - row.import_kwh
            + row.export_kwh,
            row.battery_kwh - row.storage_delta_kwh - row.conversion_loss_kwh,
            row.battery_kwh - row.actual_battery_kw * hours,
            row.storage_delta_kwh - 10 * (row.soc_after - row.soc_before),
        )
        if any(abs(value) > ENERGY_TOL for value in residuals):
            raise ValueError("ledger energy identity failed")
        if (
            abs(row.load_kw + row.actual_battery_kw - row.delivered_pv_kw - row.grid_kw)
            > POWER_TOL
        ):
            raise ValueError("ledger power identity failed")
        if not 0.2 - SOC_TOL <= row.soc_after <= 1 + SOC_TOL:
            raise ValueError("SOC outside hard boundary")
        if abs(row.actual_battery_kw) > 3 + POWER_TOL:
            raise ValueError("PCS power limit violated")
        if row.delivered_pv_kw > min(row.available_pv_kw, 6) + POWER_TOL:
            raise ValueError("PV capability exceeded")
        end, soc = row.end_s, row.soc_after


def window_totals(
    rows: tuple[CurtailmentRow, ...], start: float, end: float
) -> dict[str, float]:
    """Split ledger quantities by overlap, never integrate sampled display points."""
    if not 0 <= start < end <= DAY_SECONDS:
        raise ValueError("invalid aggregation window")
    pieces = [
        (row, max(start, row.start_s), min(end, row.end_s))
        for row in rows
        if row.start_s < end and row.end_s > start
    ]
    covered = fsum(b - a for _, a, b in pieces)
    if abs(covered - (end - start)) > TIME_TOL:
        raise ValueError("window not covered")
    # Window clipping uses the retained local coordinate, not interpolation of
    # a coalesced mean row. This keeps import/export and short peaks separate.
    physical = []
    for row, a, b in pieces:
        for audit in physical_audit_rows((row,)):
            if audit.physical_parts:
                part = audit.physical_parts[0]
                lo = (
                    part.start_s
                    if a == row.start_s
                    else max(part.start_s, a - part.origin_s)
                )
                hi = (
                    part.end_s if b == row.end_s else min(part.end_s, b - part.origin_s)
                )
                if hi <= lo:
                    continue
                duration = hi - lo
                end_fraction = (hi - part.start_s) / (part.end_s - part.start_s)
            else:
                duration = b - a
                end_fraction = (b - row.start_s) / row.duration_s
            physical.append((audit, duration, end_fraction))
    totals = {
        key: fsum(
            getattr(row, key) * (duration / row.duration_s)
            for row, duration, _ in physical
        )
        for key in ENERGIES
    }
    totals["charge_kwh"] = fsum(
        max(row.actual_battery_kw, 0) * duration / 3600 for row, duration, _ in physical
    )
    totals["discharge_kwh"] = fsum(
        max(-row.actual_battery_kw, 0) * duration / 3600
        for row, duration, _ in physical
    )
    for key in POWERS:
        totals[f"average_{key}"] = fsum(
            getattr(row, key) * duration for row, duration, _ in physical
        ) / (end - start)
    last, _, fraction = physical[-1]
    totals["soc_end"] = last.soc_before + fraction * (last.soc_after - last.soc_before)
    totals["reserve_gap_kwh"] = 10 * max(last.reserve_target_soc - totals["soc_end"], 0)
    totals["export_peak_kw"] = max(max(-row.grid_kw, 0) for row, _, _ in physical)
    return totals


def _sample_row(row: CurtailmentRow, at: float) -> tuple[float, float, float]:
    """A view samples the local subpiece, never a merged-row SOC straight line."""
    if at == row.start_s and row.physical_parts:
        part = row.physical_parts[0]
        return part.soc_before, part.actual_battery_kw, part.grid_kw
    if at == row.end_s:
        return row.soc_after, row.actual_battery_kw, row.grid_kw
    for part in row.physical_parts:
        local = at - part.origin_s
        if part.start_s <= local < part.end_s:
            fraction = (local - part.start_s) / (part.end_s - part.start_s)
            return (
                part.soc_before + fraction * (part.soc_after - part.soc_before),
                part.actual_battery_kw,
                part.grid_kw,
            )
    if row.physical_parts:
        raise ValueError("view timestamp has no physical part")
    fraction = (at - row.start_s) / row.duration_s
    return (
        row.soc_before + fraction * (row.soc_after - row.soc_before),
        row.actual_battery_kw,
        row.grid_kw,
    )


def report_status(result: JointResult) -> tuple[str, tuple[str, ...]]:
    reasons: list[str] = []
    facts = result.execution.case.segments
    if any(b.start - a.start < 97 for a, b in pairwise(facts)):
        reasons.append(
            "NOT_COVERED: dense fact changes have no isolated response window"
        )
    if DAY_SECONDS - facts[-1].start < 97:
        reasons.append(
            "INCOMPLETE_RESPONSE: final fact has insufficient observation window"
        )
    if any(item.censored for item in result.event_outcomes):
        reasons.append(
            "INCOMPLETE_RESPONSE: an event window ends with an active violation"
        )
    if not result.passed:
        return "FAIL", tuple(reasons)
    return ("INCONCLUSIVE" if reasons else "PASS"), tuple(reasons)


def _write_csv(path: Path, records: list[dict[str, object]]) -> None:
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def _power_curve(result: JointResult, path: Path) -> None:
    root = ET.Element(
        "svg",
        xmlns="http://www.w3.org/2000/svg",
        width="1200",
        height="500",
        viewBox="0 0 1200 500",
    )
    ET.SubElement(root, "rect", width="1200", height="500", fill="white")
    ET.SubElement(
        root, "text", x="35", y="25"
    ).text = "UTC 2026-01-01 00:00 to 2026-01-02 00:00 (Shanghai 08:00 to 08:00)"
    ET.SubElement(
        root, "text", x="35", y="45"
    ).text = (
        "Interval-mean power; sub-ULP peaks/durations retained in physical_parts.csv"
    )
    for index, (key, color) in enumerate(
        zip(
            POWERS,
            (
                "#555",
                "#ba8500",
                "#165dba",
                "#d29400",
                "#008c40",
                "#b64bb6",
                "#444444",
                "#d33333",
            ),
            strict=True,
        )
    ):
        points = " ".join(
            f"{40 + t / DAY_SECONDS * 1120:.4f},{260 - getattr(row, key) * 25:.4f}"
            for row in result.execution.ledger
            for t in (row.start_s, row.end_s)
        )
        ET.SubElement(
            root,
            "polyline",
            attrib={"data-series": key},
            points=points,
            fill="none",
            stroke=color,
        )
        ET.SubElement(
            root,
            "text",
            x=str(40 + (index % 4) * 280),
            y=str(460 + (index // 4) * 20),
            fill=color,
        ).text = key
    ET.ElementTree(root).write(path, encoding="unicode")


def write_daily_output(
    result: JointResult, output: Path, *, record_period_s: int, display_period_s: int
) -> dict[str, object]:
    rows = result.execution.ledger
    validate_ledger(rows)
    write_evidence(result, output)
    _write_csv(
        output / "physical_parts.csv",
        [
            {"ledger_row": index, **asdict(part)}
            for index, row in enumerate(rows)
            for part in row.physical_parts
        ],
    )
    hourly: list[dict[str, object]] = []
    for hour in range(24):
        hourly.append(
            {
                "interval_start_utc": (START_UTC + timedelta(hours=hour)).isoformat(),
                "interval_end_utc": (START_UTC + timedelta(hours=hour + 1)).isoformat(),
                **window_totals(rows, hour * 3600, (hour + 1) * 3600),
            }
        )
    _write_csv(output / "joint_hourly.csv", hourly)
    for name, period in (("record", record_period_s), ("display", display_period_s)):
        times = sorted(
            set(range(0, DAY_SECONDS, period))
            | {0, DAY_SECONDS}
            | {row.start_s for row in rows}
            | {row.end_s for row in rows}
        )
        index = 0
        views: list[dict[str, object]] = []
        for at in times:
            while index + 1 < len(rows) and at >= rows[index].end_s:
                index += 1
            row = rows[index]
            soc, actual, grid = _sample_row(row, at)
            views.append(
                {
                    "at_s": at,
                    "soc": soc,
                    "actual_battery_kw": None if at == DAY_SECONDS else actual,
                    "grid_kw": None if at == DAY_SECONDS else grid,
                }
            )
        _write_csv(output / f"joint_{name}_view.csv", views)
    _power_curve(result, output / "joint_power.svg")
    status, reasons = report_status(result)
    summary: dict[str, object] = {
        "schema": "joint_daily_v1",
        "utc_start": START_UTC.isoformat(),
        "utc_end": (START_UTC + timedelta(days=1)).isoformat(),
        "shanghai_window": (
            "2026-01-01 08:00 to 2026-01-02 08:00 +08:00; not a Shanghai civil day"
        ),
        "strategy": "joint_reserve_v1",
        "assessment": status,
        "limitations": reasons,
        "settings": asdict(result.execution.settings),
        "ems_decisions": [asdict(item) for item in result.execution.decisions],
        "totals": window_totals(rows, 0, DAY_SECONDS),
        "findings": [asdict(item) for item in result.findings],
        "budgets": {
            "permission_gate_s": 90,
            "existing_excursion_s": 96,
            "limited_full_response_envelope_s": 97,
            "envelope_is_not_a_waiver": True,
        },
        "pause_resume": "not implemented; each invocation recomputes from t=0",
        "time_representation": (
            "Positive-width display rows; retained origin+local physical parts "
            "are authoritative for energy, SOC, peak and duration. Display power "
            "is interval mean, not an instantaneous peak."
        ),
    }
    with (output / "joint_summary.json").open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2, allow_nan=False)
    return summary
