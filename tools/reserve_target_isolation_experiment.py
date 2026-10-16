"""Offline three-trajectory reserve-target experiment; no execution changes."""

import argparse
import gzip
import hashlib
import json
from dataclasses import asdict, dataclass, replace
from itertools import pairwise
from pathlib import Path

from tools.dynamic_constraint_probe import Case, FactSegment
from tools.joint_daily_output import report_status
from tools.joint_execution_contract import (
    DAY_SECONDS,
    TIME_TOL,
    JointExecutionContext,
    validate_daily_case,
)
from tools.joint_strategy_adapter import BASIC, JOINT
from tools.joint_strategy_comparison import (
    metrics,
    positive_linear_mean,
    run_strategy,
)
from tools.pv_curtailment_probe import physical_audit_rows
from tools.pv_grid_charge_joint_probe import JointResult

SOURCE_SHA256 = "3b37c192d720b4f9608693240ee87643b1ed9f7dabc55653baa3d3a1c32cc10a"
BOUNDARY_S = 64800
BATTERY_CAPACITY_KWH = 10.0
DECISIONS = tuple(range(0, DAY_SECONDS, 3600))


@dataclass(frozen=True, slots=True)
class GapSlice:
    start_s: float
    duration_s: float
    soc_before: float
    soc_after: float


def _source_case(raw: object) -> Case:
    if not isinstance(raw, dict) or set(raw) != {"name", "initial_soc", "segments"}:
        raise ValueError("unexpected source case schema")
    segments = raw["segments"]
    if not isinstance(segments, list):
        raise ValueError("source segments must be a list")
    expected = set(FactSegment.__dataclass_fields__)
    facts = []
    for segment in segments:
        if not isinstance(segment, dict) or set(segment) != expected:
            raise ValueError("unexpected source fact schema")
        facts.append(FactSegment(**segment))
    case = Case(raw["name"], raw["initial_soc"], tuple(facts))
    validate_daily_case(case, JointExecutionContext())
    return case


def build_cases(source_bytes: bytes) -> tuple[Case, Case]:
    if hashlib.sha256(source_bytes).hexdigest() != SOURCE_SHA256:
        raise ValueError("frozen inputs.json SHA-256 differs")
    data = json.loads(source_bytes)
    if not isinstance(data, dict) or set(data) != {"original", "reserve"}:
        raise ValueError("unexpected input scenario names")
    b = _source_case(data["reserve"])
    changes = [
        (fact.start, fact.reserve_target_soc)
        for i, fact in enumerate(b.segments)
        if i == 0 or fact.reserve_target_soc != b.segments[i - 1].reserve_target_soc
    ]
    if changes != [(0, 0.8), (BOUNDARY_S, 0.9)]:
        raise ValueError("B target schedule differs from the frozen source")
    if b.initial_soc != 0.5 or b.segments[-1].end != DAY_SECONDS:
        raise ValueError("initial SOC or day boundary changed")
    a = replace(
        b,
        name="reserve_target_20_percent",
        segments=tuple(replace(fact, reserve_target_soc=0.2) for fact in b.segments),
    )
    for left, right in zip(a.segments, b.segments, strict=True):
        if replace(left, reserve_target_soc=right.reserve_target_soc) != right:
            raise AssertionError("A changed a fact other than the soft target")
    return a, b


def common_target_gap(
    slices: tuple[GapSlice, ...], final_soc: float
) -> dict[str, float]:
    """Evaluate saved SOC against B's target; never feed this back to control."""
    total_s = 0.0
    area = 0.0
    peak = 0.0
    expected_start = 0.0
    for piece in slices:
        start = piece.start_s
        end = start + piece.duration_s
        if piece.duration_s <= 0 or abs(start - expected_start) > TIME_TOL:
            raise ValueError("SOC pieces must be positive, contiguous and ordered")
        if end > DAY_SECONDS + TIME_TOL:
            raise ValueError("SOC piece exceeds the day")
        boundaries = [start]
        if start < BOUNDARY_S < end:
            boundaries.append(float(BOUNDARY_S))
        boundaries.append(end)
        for lo, hi in pairwise(boundaries):
            fraction_lo = (lo - start) / piece.duration_s
            fraction_hi = (hi - start) / piece.duration_s
            before = (
                piece.soc_before + (piece.soc_after - piece.soc_before) * fraction_lo
            )
            after = (
                piece.soc_before + (piece.soc_after - piece.soc_before) * fraction_hi
            )
            target = 0.8 if lo < BOUNDARY_S else 0.9
            peak = max(
                peak, BATTERY_CAPACITY_KWH * max(0.0, target - min(before, after))
            )
            area += (
                BATTERY_CAPACITY_KWH
                * positive_linear_mean(target - before, target - after)
                * (hi - lo)
                / 3600
            )
        total_s += piece.duration_s
        expected_start = end
    if (
        abs(total_s - DAY_SECONDS) > TIME_TOL
        or abs(expected_start - DAY_SECONDS) > TIME_TOL
    ):
        raise ValueError("SOC pieces do not cover the complete day")
    return {
        "terminal_kwh": BATTERY_CAPACITY_KWH * max(0.0, 0.9 - final_soc),
        "peak_kwh": peak,
        "integral_kwh_h": area,
    }


def _gap_slices(result: JointResult) -> tuple[GapSlice, ...]:
    return tuple(
        GapSlice(row.start_s, row.duration_s, row.soc_before, row.soc_after)
        for row in physical_audit_rows(result.execution.ledger)
    )


def run_experiment(inputs_path: Path, output_dir: Path) -> dict[str, object]:
    source_bytes = inputs_path.read_bytes()
    a, b = build_cases(source_bytes)
    if output_dir.exists():
        raise FileExistsError("experiment output directory already exists")
    output_dir.mkdir(parents=True)
    records = []
    for name, case, strategy in (
        ("A_joint_20_percent", a, JOINT),
        ("B_joint_original_target", b, JOINT),
        ("fixed_basic_reference", b, BASIC),
    ):
        result = run_strategy(
            case, strategy, mode="dynamic", step_s=60, record_s=60, display_s=5
        )
        values = metrics(result)
        decision_times = tuple(decision.at for decision in result.execution.decisions)
        if decision_times != DECISIONS:
            raise AssertionError("EMS decision schedule changed")
        common = common_target_gap(_gap_slices(result), result.execution.final_soc)
        own = {
            "terminal_kwh": values["reserve_gap_kwh"],
            "peak_kwh": values["reserve_peak_gap_kwh"],
            "integral_kwh_h": values["reserve_deficit_kwh_h"],
        }
        if case is b:
            tolerances = {
                "terminal_kwh": 2.4e-8,
                "peak_kwh": 2.4e-8,
                "integral_kwh_h": 2.4e-7,
            }
            for key, tolerance in tolerances.items():
                if abs(common[key] - own[key]) > tolerance:
                    raise AssertionError(
                        f"fixed B-target evaluation disagrees for {name}/{key}"
                    )
        status, limitations = report_status(result)
        archive = f"{name}.json.gz"
        with gzip.open(output_dir / archive, "wt", encoding="utf-8") as stream:
            json.dump(asdict(result), stream, ensure_ascii=False, allow_nan=False)
        records.append(
            {
                "name": name,
                "strategy": strategy,
                "target_schedule": [[0, 0.2]]
                if case is a
                else [[0, 0.8], [BOUNDARY_S, 0.9]],
                "assessment": status,
                "limitations": limitations,
                "own_target_gap": own,
                "common_B_target_gap": common,
                "metrics": values,
                "decision_times_s": decision_times,
                "trajectory": archive,
                "excursions": [asdict(x) for x in result.excursions],
                "findings": [asdict(x) for x in result.findings],
            }
        )
    summary: dict[str, object] = {
        "source_inputs_path": str(inputs_path),
        "source_inputs_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "candidate": "52bc03593fe52d055d23d7f7d05da90ee439ba52",
        "mode": "dynamic",
        "physical_step_s": 60,
        "record_period_s": 60,
        "display_period_s": 5,
        "records": records,
        "limitations": [
            "Offline synthetic comparison, not field or hardware validation",
            "Common B-target gaps are postprocessing only and never affect control",
            "Dynamic export and response-period grid charging remain recorded",
            "Example tariffs and terminal values are not real savings",
        ],
    }
    (output_dir / "comparison.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    if any(record["assessment"] != "PASS" for record in records):
        raise AssertionError("one or more original safety/budget assessments failed")
    (output_dir / "COMPLETE").write_text(
        "three trajectories audited\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    run_experiment(args.inputs, args.output_dir)


if __name__ == "__main__":
    main()
