"""One-factor offline comparison of the B case's morning grid-charge cutoff."""

import argparse
import gzip
import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import cast

from ems_simulator.demo import TARIFF_PROFILE_CNY_PER_KWH
from tools.dynamic_constraint_probe import Case
from tools.joint_daily_output import report_status
from tools.joint_execution_contract import (
    DAY_ENERGY_TOL,
    DAY_SECONDS,
    JointExecutionContext,
    validate_daily_case,
)
from tools.joint_strategy_adapter import JOINT
from tools.joint_strategy_comparison import (
    EXPORT_PRICE,
    VALUATIONS,
    metric_tolerance,
    metrics,
    run_strategy,
)
from tools.reserve_target_isolation_experiment import (
    SOURCE_SHA256,
    _gap_slices,
    build_cases,
    common_target_gap,
)

ORIGINAL_CUTOFF_S = 21600
CANDIDATE_CUTOFF_S = 18000
EXPECTED_PERMISSION_EVENTS = (
    (0, True),
    (5400, False),
    (7200, True),
    (ORIGINAL_CUTOFF_S, False),
    (64800, True),
)
EXPECTED_CANDIDATE_EVENTS = (
    (0, True),
    (5400, False),
    (7200, True),
    (CANDIDATE_CUTOFF_S, False),
    (64800, True),
)
EXPECTED_DECISIONS = tuple(range(0, DAY_SECONDS, 3600))
GAP_TOLERANCES = {
    "terminal_kwh": DAY_ENERGY_TOL,
    "peak_kwh": DAY_ENERGY_TOL,
    "integral_kwh_h": 2.4e-7,
}


def permission_events(case: Case) -> tuple[tuple[int, bool], ...]:
    """Return the permission changes, not every unrelated hourly fact boundary."""
    return tuple(
        (fact.start, fact.grid_charge_allowed)
        for index, fact in enumerate(case.segments)
        if index == 0
        or fact.grid_charge_allowed != case.segments[index - 1].grid_charge_allowed
    )


def build_pair(source_bytes: bytes) -> tuple[Case, Case]:
    """Verify frozen source and move exactly one permission-off event."""
    _, baseline = build_cases(source_bytes)
    if permission_events(baseline) != EXPECTED_PERMISSION_EVENTS:
        raise ValueError("B permission events differ from frozen source")
    changed = 0
    facts = []
    for fact in baseline.segments:
        if fact.start == CANDIDATE_CUTOFF_S:
            if fact.end != ORIGINAL_CUTOFF_S or not fact.grid_charge_allowed:
                raise ValueError("cutoff interval differs from frozen source")
            facts.append(replace(fact, grid_charge_allowed=False))
            changed += 1
        else:
            facts.append(fact)
    if changed != 1:
        raise ValueError("cutoff interval is not unique")
    candidate = replace(baseline, segments=tuple(facts))
    validate_pair(baseline, candidate)
    return baseline, candidate


def validate_pair(baseline: Case, candidate: Case) -> None:
    """Reject a changed fact, strategy input, boundary, or extra event."""
    validate_daily_case(baseline, JointExecutionContext())
    validate_daily_case(candidate, JointExecutionContext())
    if baseline.name != candidate.name or baseline.initial_soc != candidate.initial_soc:
        raise ValueError("case identity or initial SOC changed")
    if len(baseline.segments) != len(candidate.segments):
        raise ValueError("fact boundaries changed")
    changed = []
    for left, right in zip(baseline.segments, candidate.segments, strict=True):
        if left == right:
            continue
        if replace(right, grid_charge_allowed=left.grid_charge_allowed) != left:
            raise ValueError("a non-permission fact changed")
        changed.append(
            (left.start, left.end, left.grid_charge_allowed, right.grid_charge_allowed)
        )
    if changed != [(CANDIDATE_CUTOFF_S, ORIGINAL_CUTOFF_S, True, False)]:
        raise ValueError("the cutoff is not the sole input difference")
    if permission_events(baseline) != EXPECTED_PERMISSION_EVENTS:
        raise ValueError("unexpected baseline permission schedule")
    if permission_events(candidate) != EXPECTED_CANDIDATE_EVENTS:
        raise ValueError("unexpected candidate permission schedule")


def compare_outcomes(
    baseline: dict[str, object], candidate: dict[str, object]
) -> dict[str, object]:
    """Report tradeoffs without turning a synthetic result into a winner."""
    raw_base_gap = baseline["common_B_target_gap"]
    raw_candidate_gap = candidate["common_B_target_gap"]
    raw_base_metrics = baseline["metrics"]
    raw_candidate_metrics = candidate["metrics"]
    if not all(
        isinstance(item, dict)
        for item in (
            raw_base_gap,
            raw_candidate_gap,
            raw_base_metrics,
            raw_candidate_metrics,
        )
    ):
        raise TypeError("missing audit metrics")
    base_gap = cast(dict[str, float], raw_base_gap)
    candidate_gap = cast(dict[str, float], raw_candidate_gap)
    base_metrics = cast(dict[str, float], raw_base_metrics)
    candidate_metrics = cast(dict[str, float], raw_candidate_metrics)
    gap_delta = {key: candidate_gap[key] - base_gap[key] for key in GAP_TOLERANCES}
    gap_worsened = {
        key: delta > GAP_TOLERANCES[key] for key, delta in gap_delta.items()
    }
    net_cost_delta = candidate_metrics["net_cost_cny"] - base_metrics["net_cost_cny"]
    curtailment_delta = (
        candidate_metrics["curtailed_pv_kwh"] - base_metrics["curtailed_pv_kwh"]
    )
    prohibited_delta = (
        candidate_metrics["prohibited_grid_charge_kwh"]
        - base_metrics["prohibited_grid_charge_kwh"]
    )
    audits_pass = baseline["assessment"] == candidate["assessment"] == "PASS"
    return {
        "candidate_minus_baseline_common_gap": gap_delta,
        "common_gap_worsened": gap_worsened,
        "candidate_minus_baseline_net_cost_cny": net_cost_delta,
        "candidate_minus_baseline_curtailment_kwh": curtailment_delta,
        "candidate_minus_baseline_prohibited_grid_charge_kwh": prohibited_delta,
        "audits_pass": audits_pass,
        "non_worsening_guarded_improvement": (
            audits_pass
            and not any(gap_worsened.values())
            and prohibited_delta <= DAY_ENERGY_TOL
            and (
                net_cost_delta < -metric_tolerance("net_cost_cny")
                or curtailment_delta < -DAY_ENERGY_TOL
            )
        ),
        "interpretation_limit": (
            "A lower synthetic bill is not a real saving or a strategy winner; "
            "compare terminal inventory and all common-target gaps."
        ),
    }


def run_experiment(inputs_path: Path, output_dir: Path) -> dict[str, object]:
    source_bytes = inputs_path.read_bytes()
    baseline, candidate = build_pair(source_bytes)
    output_dir.mkdir(parents=True, exist_ok=False)
    records: list[dict[str, object]] = []
    for label, case in (("B_original", baseline), ("B_earlier_cutoff", candidate)):
        result = run_strategy(
            case, JOINT, mode="dynamic", step_s=60, record_s=60, display_s=5
        )
        values = metrics(result)  # Includes ledger, SOC, PCS and energy checks.
        decisions = tuple(item.at for item in result.execution.decisions)
        if decisions != EXPECTED_DECISIONS:
            raise AssertionError("the hourly EMS decision schedule changed")
        status, limitations = report_status(result)
        archive = f"{label}.json.gz"
        with gzip.open(output_dir / archive, "wt", encoding="utf-8") as stream:
            json.dump(asdict(result), stream, ensure_ascii=False, allow_nan=False)
        records.append(
            {
                "name": label,
                "assessment": status,
                "limitations": limitations,
                "common_B_target_gap": common_target_gap(
                    _gap_slices(result), result.execution.final_soc
                ),
                "metrics": values,
                "decision_times_s": decisions,
                "trajectory": archive,
                "excursions": [asdict(item) for item in result.excursions],
                "findings": [asdict(item) for item in result.findings],
            }
        )
    summary: dict[str, object] = {
        "source_inputs_path": str(inputs_path),
        "source_inputs_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "source_expected_sha256": SOURCE_SHA256,
        "baseline_commit": "6b0877ba074d258da950ff86fd5792efeb8fa94d",
        "single_changed_event": {
            "field": "grid_charge_allowed",
            "from_at_s": ORIGINAL_CUTOFF_S,
            "to_at_s": CANDIDATE_CUTOFF_S,
            "value": False,
        },
        "baseline_permission_events": EXPECTED_PERMISSION_EVENTS,
        "candidate_permission_events": EXPECTED_CANDIDATE_EVENTS,
        "mode": "dynamic",
        "physical_step_s": 60,
        "control_period_s": 3600,
        "record_period_s": 60,
        "display_period_s": 5,
        "strategy": JOINT,
        "tariff": {
            "currency": "CNY",
            "synthetic": True,
            "import_per_kwh": TARIFF_PROFILE_CNY_PER_KWH,
            "import_source": "ems_simulator/demo.py",
            "export_per_kwh": EXPORT_PRICE,
            "terminal_inventory_valuation_prices_cny_per_kwh": VALUATIONS,
        },
        "records": records,
        "comparison": compare_outcomes(records[0], records[1]),
        "limitations": [
            "Offline synthetic model; not real savings, hardware or field validation.",
            "Response-period export and prohibited grid charging remain in the ledger.",
            "PASS means only the existing dynamic safety budgets, "
            "not instantaneous zero export.",
            "A complete run starts at t=0; pause/resume is not implemented.",
            "Terminal inventory and its assumed value must be reported separately.",
        ],
    }
    (output_dir / "comparison.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    if any(record["assessment"] != "PASS" for record in records):
        raise AssertionError(
            "one or both original safety audits failed; evidence retained"
        )
    (output_dir / "COMPLETE").write_text(
        "both predefined dynamic audits passed; comparison does not assert a winner\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    run_experiment(args.inputs, args.output_dir)


if __name__ == "__main__":
    main()
