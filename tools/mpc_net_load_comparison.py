"""Fixed offline planner comparison through the single accepted executor."""

import argparse
import gzip
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from tools.joint_daily_output import report_status
from tools.joint_execution_contract import JointExecutionContext
from tools.joint_mpc_adapter import NET_LOAD_BASELINE, PRICE_BASELINE, mpc_strategy
from tools.joint_strategy_adapter import MPC
from tools.joint_strategy_comparison import metrics
from tools.mpc_load_bias_experiment import (
    BASELINE,
    DECISIONS,
    GAP_TOL,
    _json_default,
    _write_json,
    compare,
    forecast_pair,
)
from tools.pv_grid_charge_joint_probe import run_joint
from tools.reserve_target_isolation_experiment import (
    SOURCE_SHA256,
    _gap_slices,
    build_cases,
    common_target_gap,
)

# Already accepted, pre-selection price trajectory; not a newly generated oracle.
REFERENCE_SHA256 = "1292f84424713ac1da1af3ca462b2ab193301ee6f269b8174d176df6b0de1338"
FORECAST_REFERENCE_SHA256 = (
    "8f4c2784dfdb49e6a587547a4221b9bb49f0cabfadc7d22d99db9a633c86c9b4"
)
LABELS = ("price_default_A", "price_explicit_A", "net_load_A", "net_load_B")


def read_reference(path: Path) -> dict:
    if hashlib.sha256(path.read_bytes()).hexdigest() != REFERENCE_SHA256:
        raise ValueError("price compatibility reference hash differs")
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def run_comparison(inputs: Path, reference: Path, output: Path) -> dict[str, object]:
    if output.exists():
        raise FileExistsError("output exists; no overwrite or implicit repeat")
    old_price = read_reference(reference)
    source = inputs.read_bytes()
    _, case = build_cases(source)
    a, b = forecast_pair()  # Original clocks/values; only B load is multiplied by 1.2.
    old_inputs_path = reference.parent / "frozen-inputs.json"
    if (
        hashlib.sha256(old_inputs_path.read_bytes()).hexdigest()
        != FORECAST_REFERENCE_SHA256
    ):
        raise ValueError("original forecast artifact hash differs")
    old_inputs = json.loads(old_inputs_path.read_text(encoding="utf-8"))
    for key, frames in (("A_forecasts", a), ("B_forecasts", b)):
        serialized = json.loads(
            json.dumps([asdict(f) for f in frames], default=_json_default)
        )
        if serialized != old_inputs[key]:
            raise ValueError("forecast values or clocks differ from frozen A/B")
    context = JointExecutionContext(strategy=MPC)
    if old_price["execution"]["case"] != json.loads(json.dumps(asdict(case))):
        raise ValueError("reference actual case differs")
    strategies = (
        mpc_strategy(a),
        mpc_strategy(a, planner=PRICE_BASELINE),
        mpc_strategy(a, planner=NET_LOAD_BASELINE),
        mpc_strategy(b, planner=NET_LOAD_BASELINE),
    )
    output.mkdir(parents=True, exist_ok=False)
    (output / "source-inputs.json").write_bytes(source)
    _write_json(
        output / "frozen-inputs.json",
        {
            "baseline": BASELINE,
            "source_sha256": SOURCE_SHA256,
            "reference": str(reference),
            "reference_sha256": REFERENCE_SHA256,
            "forecast_reference_sha256": FORECAST_REFERENCE_SHA256,
            "settlement": old_inputs["settlement"],
            "tolerances": old_inputs["tolerances"],
            "shared_actual_case": asdict(case),
            "shared_context": asdict(context),
            "A_forecasts": [asdict(f) for f in a],
            "B_forecasts": [asdict(f) for f in b],
            "matrix": dict(zip(LABELS, [s.planner for s in strategies], strict=True)),
            "mode": "dynamic",
            "physical_step_s": 60,
            "record_s": 60,
            "display_s": 5,
            "decision_times_s": DECISIONS,
            "only_net_B_input_difference": "96 forecast loads 1.25 -> 1.5 kW",
            "comparison_contract": "SIM_TIME_ENERGY_NET_LOAD_MPC_ADAPTER.md",
        },
    )
    records = []
    for label, strategy in zip(LABELS, strategies, strict=True):
        result = run_joint(
            case,
            mode="dynamic",
            physical_step_s=60,
            record_period_s=60,
            display_period_s=5,
            context=context,
            strategy=strategy,
        )
        # Save the entire original result before accepting any metric or budget.
        raw = json.loads(
            json.dumps(asdict(result), allow_nan=False, default=_json_default)
        )
        archive = output / f"{label}.json.gz"
        with gzip.open(archive, "wt", encoding="utf-8") as stream:
            json.dump(raw, stream, ensure_ascii=False, allow_nan=False)
        compatibility = raw == old_price if label.startswith("price_") else None
        values = metrics(result)
        gap = common_target_gap(_gap_slices(result), result.execution.final_soc)
        own = {
            "terminal_kwh": values["reserve_gap_kwh"],
            "peak_kwh": values["reserve_peak_gap_kwh"],
            "integral_kwh_h": values["reserve_deficit_kwh_h"],
        }
        if any(abs(gap[k] - own[k]) > tol for k, tol in GAP_TOL.items()):
            raise AssertionError("common B target accounting differs")
        if tuple(d.at for d in result.execution.decisions) != DECISIONS:
            raise AssertionError("EMS cadence differs")
        settings = asdict(result.execution.settings)
        if json.loads(json.dumps(settings)) != old_price["execution"]["settings"]:
            raise AssertionError("executor settings differ from accepted reference")
        status, limits = report_status(result)
        record = {
            "label": label,
            "planner": strategy.planner,
            "assessment": status,
            "full_price_reference_equal": compatibility,
            "metrics": values,
            "common_B_target_gap": gap,
            "limitations": limits,
            "decision_times_s": DECISIONS,
            "decisions": [asdict(d) for d in result.execution.decisions],
            "settings": settings,
            "excursions": [asdict(e) for e in result.excursions],
            "event_outcomes": [asdict(e) for e in result.event_outcomes],
            "findings": [asdict(f) for f in result.findings],
            "trajectory": archive.name,
            "trajectory_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        }
        _write_json(output / f"{label}-summary.json", record)
        records.append(record)
        if compatibility is False:
            raise AssertionError(
                "default price behavior changed; raw evidence retained"
            )
    saved = [
        json.loads((output / f"{label}-summary.json").read_text(encoding="utf-8"))
        for label in LABELS
    ]
    summary = {
        "baseline": BASELINE,
        "records": records,
        "net_A_minus_price_A": compare(saved[0]["metrics"], saved[2]["metrics"]),
        "net_B_minus_net_A": compare(saved[2]["metrics"], saved[3]["metrics"]),
        "net_B_minus_net_A_common_gap": compare(
            saved[2]["common_B_target_gap"], saved[3]["common_B_target_gap"]
        ),
        "limitations": [
            "Offline synthetic forecasts; not prediction-source certification.",
            "Existing net-load rule is not a new optimizer or reserve guarantee.",
            "Budget PASS does not mean zero transient export or grid-charge violation.",
            "Forecast prices differ from unchanged synthetic settlement tariffs.",
            "Terminal inventory and valuation sensitivities must accompany cost.",
            "No field-safety, realized-savings, degradation or pause/resume claim.",
        ],
    }
    _write_json(output / "comparison.json", summary)
    if any(r["assessment"] != "PASS" for r in records):
        raise AssertionError("dynamic budget not PASS; all four records retained")
    (output / "COMPLETE").write_text("four scenario audits PASS\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    run_comparison(args.inputs, args.reference, args.output_dir)


if __name__ == "__main__":
    main()
