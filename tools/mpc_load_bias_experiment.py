"""Frozen two-trajectory MPC load-forecast sensitivity; no executor changes."""

import argparse
import gzip
import hashlib
import json
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from pathlib import Path

from ems_simulator.demo import TARIFF_PROFILE_CNY_PER_KWH
from forecast import ForecastHorizon, ForecastPoint
from tools.joint_daily_output import report_status
from tools.joint_execution_contract import (
    DAY_ENERGY_TOL,
    DAY_SECONDS,
    ENERGY_TOL,
    POWER_TOL,
    SOC_TOL,
    START_UTC,
    TIME_TOL,
    JointExecutionContext,
)
from tools.joint_mpc_adapter import IssuedMPCForecast, mpc_strategy
from tools.joint_strategy_adapter import MPC
from tools.joint_strategy_comparison import EXPORT_PRICE, VALUATIONS, metrics
from tools.pv_grid_charge_joint_probe import run_joint
from tools.reserve_target_isolation_experiment import (
    SOURCE_SHA256,
    _gap_slices,
    build_cases,
    common_target_gap,
)

BASELINE = "2e5c8b4e7be09102aa7d01238e4a273d2772075f"
LOAD_MULTIPLIER = 1.2
DECISIONS = tuple(range(0, DAY_SECONDS, 3600))
GAP_TOL = {
    "terminal_kwh": DAY_ENERGY_TOL,
    "peak_kwh": DAY_ENERGY_TOL,
    "integral_kwh_h": 2.4e-7,
}


def original_forecasts() -> tuple[IssuedMPCForecast, ...]:
    """Reuse the committed test's default synthetic schedule, not case truth.

    Source: tests/integration/test_joint_mpc_adapter.py::_forecasts at BASELINE.
    Forecast price is a constant over each four-hour frame; settlement still
    uses the separate existing actual demo tariff. These are not real forecasts.
    """
    frames = []
    for hour in range(24):
        decision = START_UTC + timedelta(hours=hour)
        price = 0.3 if hour == 0 else 0.9 if hour == 1 else 0.55
        horizon = ForecastHorizon(
            tuple(
                ForecastPoint(decision + timedelta(hours=offset), 0.25, 1.25, price)
                for offset in range(4)
            )
        )
        frames.append(
            IssuedMPCForecast(
                decision,
                decision - timedelta(minutes=5),
                decision,
                decision,
                decision + timedelta(hours=4),
                horizon,
            )
        )
    return tuple(frames)


def forecast_pair() -> tuple[
    tuple[IssuedMPCForecast, ...], tuple[IssuedMPCForecast, ...]
]:
    original = original_forecasts()
    biased = tuple(
        replace(
            frame,
            horizon=ForecastHorizon(
                tuple(
                    replace(point, load_power_kw=point.load_power_kw * LOAD_MULTIPLIER)
                    for point in frame.horizon.points
                )
            ),
        )
        for frame in original
    )
    validate_pair(original, biased)
    return original, biased


def validate_pair(
    a: tuple[IssuedMPCForecast, ...], b: tuple[IssuedMPCForecast, ...]
) -> None:
    """Exact input-difference guard, independent of simulation outcomes."""
    if a != original_forecasts() or len(b) != 24:
        raise ValueError("original forecast or frame count differs")
    for left, right in zip(a, b, strict=True):
        if replace(right, horizon=left.horizon) != left:
            raise ValueError("forecast clock or metadata changed")
        if len(right.horizon.points) != 4:
            raise ValueError("forecast point count changed")
        for p, q in zip(left.horizon.points, right.horizon.points, strict=True):
            if (
                replace(q, load_power_kw=p.load_power_kw) != p
                or q.load_power_kw != p.load_power_kw * LOAD_MULTIPLIER
            ):
                raise ValueError("only load forecast times 1.2 is allowed")


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def _write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(
            value,
            stream,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
            default=_json_default,
        )


def compare(a: dict[str, float], b: dict[str, float]) -> dict[str, float]:
    if a.keys() != b.keys():
        raise ValueError("metric schemas differ")
    return {key: b[key] - a[key] for key in a}


def run_experiment(inputs: Path, output: Path) -> dict[str, object]:
    if output.exists():
        raise FileExistsError("output exists; never overwrite or rerun implicitly")
    source = inputs.read_bytes()
    _, case = build_cases(source)  # Verifies exact source SHA and original B.
    a, b = forecast_pair()
    # Both validated strategies are constructed before either trajectory starts.
    strategies = (mpc_strategy(a), mpc_strategy(b))
    context = JointExecutionContext(strategy=MPC)
    output.mkdir(parents=True, exist_ok=False)
    (output / "source-inputs.json").write_bytes(source)
    frozen = {
        "baseline": BASELINE,
        "source_sha256": SOURCE_SHA256,
        "actual_case_shared_by_both": asdict(case),
        "context_shared_by_both": asdict(context),
        "A_forecasts": [asdict(f) for f in a],
        "B_forecasts": [asdict(f) for f in b],
        "only_change": "96 load_power_kw values: 1.25 -> 1.5 kW",
        "dynamic": True,
        "physical_step_s": 60,
        "record_s": 60,
        "display_s": 5,
        "decision_times_s": DECISIONS,
        "tolerances": {
            "power_kw": POWER_TOL,
            "soc": SOC_TOL,
            "time_s": TIME_TOL,
            "segment_kwh": ENERGY_TOL,
            "day_kwh": DAY_ENERGY_TOL,
            "gap": GAP_TOL,
        },
        "settlement": {
            "synthetic": True,
            "currency": "CNY",
            "import_tariff": TARIFF_PROFILE_CNY_PER_KWH,
            "export_tariff": EXPORT_PRICE,
            "terminal_values_cny_per_kwh": VALUATIONS,
        },
        "forecast_source": "committed test_joint_mpc_adapter.py::_forecasts",
    }
    _write_json(output / "frozen-inputs.json", frozen)
    records = []
    for label, strategy in zip(
        ("A_original", "B_load_plus_20pct"), strategies, strict=True
    ):
        result = run_joint(
            case,
            mode="dynamic",
            physical_step_s=60,
            record_period_s=60,
            display_period_s=5,
            context=context,
            strategy=strategy,
        )
        # Retain the unmodified result BEFORE any acceptance assertion.
        archive = output / f"{label}.json.gz"
        with gzip.open(archive, "wt", encoding="utf-8") as stream:
            json.dump(asdict(result), stream, ensure_ascii=False, allow_nan=False)
        values = metrics(result)  # Original ledger/cadence/SOC/PCS validation.
        gap = common_target_gap(_gap_slices(result), result.execution.final_soc)
        own = {
            "terminal_kwh": values["reserve_gap_kwh"],
            "peak_kwh": values["reserve_peak_gap_kwh"],
            "integral_kwh_h": values["reserve_deficit_kwh_h"],
        }
        for key, tolerance in GAP_TOL.items():
            if abs(gap[key] - own[key]) > tolerance:
                raise AssertionError(f"common target calculation differs: {key}")
        if tuple(d.at for d in result.execution.decisions) != DECISIONS:
            raise AssertionError("EMS decision cadence changed")
        status, limits = report_status(result)
        record = {
            "label": label,
            "assessment": status,
            "limitations": limits,
            "metrics": values,
            "common_B_target_gap": gap,
            "decision_times_s": DECISIONS,
            "decisions": [asdict(d) for d in result.execution.decisions],
            "settings": asdict(result.execution.settings),
            "excursions": [asdict(e) for e in result.excursions],
            "event_outcomes": [asdict(e) for e in result.event_outcomes],
            "findings": [asdict(f) for f in result.findings],
            "trajectory": archive.name,
            "trajectory_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        }
        _write_json(output / f"{label}-summary.json", record)
        records.append(record)
    # Use freshly extracted typed metrics for deltas; do not alter either ledger.
    raw_a = json.loads((output / "A_original-summary.json").read_text(encoding="utf-8"))
    raw_b = json.loads(
        (output / "B_load_plus_20pct-summary.json").read_text(encoding="utf-8")
    )
    if raw_a["settings"] != raw_b["settings"]:
        raise AssertionError("executor settings differ")
    summary = {
        "baseline": BASELINE,
        "frozen_inputs_sha256": hashlib.sha256(
            (output / "frozen-inputs.json").read_bytes()
        ).hexdigest(),
        "records": records,
        "B_minus_A_metrics": compare(raw_a["metrics"], raw_b["metrics"]),
        "B_minus_A_common_gap": compare(
            raw_a["common_B_target_gap"], raw_b["common_B_target_gap"]
        ),
        "limitations": [
            "Synthetic forecasts, neither certified accurate; no winner assumed.",
            "Forecast price and settlement tariff are separate unchanged assumptions.",
            "PASS means dynamic budgets, not zero transient violation or field safety.",
            "MPC soft-target response is measured, not assumed optimal.",
            "Terminal inventory valuation is sensitivity, not realized income.",
            "No degradation, demand, fixed charges or taxes; no pause/resume.",
        ],
    }
    _write_json(output / "comparison.json", summary)
    if any(r["assessment"] != "PASS" for r in records):
        raise AssertionError("dynamic acceptance not PASS; evidence retained")
    (output / "COMPLETE").write_text("two scenario audits PASS\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    run_experiment(args.inputs, args.output_dir)


if __name__ == "__main__":
    main()
