"""Same-facts offline comparison; one executor and post-hoc accounting only."""

import argparse
import gzip
import hashlib
import json
from dataclasses import asdict
from math import fsum
from pathlib import Path

from ems_simulator.demo import TARIFF_PROFILE_CNY_PER_KWH
from optimization.battery_planning import BatteryOptimizationModel
from optimization.export_revenue import (
    DeterministicExportRevenueCalculator,
    ExportRevenueInput,
)
from optimization.import_cost import DeterministicImportCostCalculator, ImportCostInput
from optimization.terminal_energy_value import (
    DeterministicTerminalEnergyValueCalculator,
    TerminalEnergyValueInput,
)
from tools.dynamic_constraint_probe import Case
from tools.joint_daily_output import report_status, validate_ledger, window_totals
from tools.joint_execution_contract import (
    DAY_ENERGY_TOL,
    DAY_SECONDS,
    POWER_TOL,
    SOC_TOL,
    TIME_TOL,
    DailyEvent,
    JointExecutionContext,
    daily_case,
    validate_daily_case,
)
from tools.joint_strategy_adapter import STRATEGIES, strategy_by_id
from tools.pv_curtailment_probe import physical_audit_rows
from tools.pv_grid_charge_joint_probe import JointResult, run_joint

EXPORT_PRICE = 0.0  # Existing synthetic assumption: ems_simulator/runner.py.
VALUATIONS = (0.30, 0.55, 0.90)  # Existing demo price levels, not market estimates.


def comparison_cases() -> dict[str, Case]:
    return {
        "original": daily_case(),
        "reserve": daily_case(
            events=(
                DailyEvent(0, grid_charge_allowed=True, reserve_target_soc=0.8),
                DailyEvent(5400, grid_charge_allowed=False),
                DailyEvent(7200, grid_charge_allowed=True),
                DailyEvent(21600, grid_charge_allowed=False),
                DailyEvent(64800, grid_charge_allowed=True, reserve_target_soc=0.9),
            )
        ),
    }


def run_strategy(
    case: Case,
    identifier: str,
    *,
    mode: str,
    step_s: float,
    record_s: float = 60,
    display_s: float = 5,
) -> JointResult:
    context = JointExecutionContext(strategy=identifier)
    validate_daily_case(case, context)
    return run_joint(
        case,
        mode=mode,
        physical_step_s=step_s,
        context=context,
        strategy=strategy_by_id(identifier),
        record_period_s=record_s,
        display_period_s=display_s,
    )


def price_piece(
    origin: float,
    start: float,
    end: float,
    grid_kw: float,
    prices: tuple[float, ...] = TARIFF_PROFILE_CNY_PER_KWH,
) -> tuple[float, float]:
    """Settle retained local duration, splitting at every UTC tariff boundary."""
    if len(prices) != 24 or end <= start:
        raise ValueError("invalid piece or price coverage")
    imports, exports = [], []
    for hour, price in enumerate(prices):
        lo = max(start, hour * 3600 - origin)
        hi = min(end, (hour + 1) * 3600 - origin)
        if hi <= lo:
            continue
        hours = (hi - lo) / 3600
        imports.append(
            DeterministicImportCostCalculator()
            .calculate(ImportCostInput(max(grid_kw, 0) * hours, price))
            .realized_import_cost
        )
        exports.append(
            DeterministicExportRevenueCalculator()
            .calculate(ExportRevenueInput(max(-grid_kw, 0) * hours, EXPORT_PRICE))
            .realized_export_revenue
        )
    covered = fsum(
        max(0, min(end, (h + 1) * 3600 - origin) - max(start, h * 3600 - origin))
        for h in range(24)
    )
    if abs(covered - (end - start)) > TIME_TOL:
        raise ValueError("piece outside the UTC tariff day")
    return fsum(imports), fsum(exports)


def positive_linear_mean(a: float, b: float) -> float:
    """Mean positive part of a linear deficit; do not average across zero."""
    if min(a, b) >= 0:
        return (a + b) / 2
    if max(a, b) <= 0:
        return 0.0
    return max(a, b) ** 2 / (2 * abs(b - a))


def metrics(result: JointResult) -> dict[str, float]:
    rows = result.execution.ledger
    validate_ledger(rows)
    if tuple(d.at for d in result.execution.decisions) != tuple(range(0, 86400, 3600)):
        raise AssertionError("control cadence changed")
    total = window_totals(rows, 0, DAY_SECONDS)
    pieces = physical_audit_rows(rows)
    priced = [
        price_piece(p.origin_s, p.start_s, p.end_s, p.grid_kw)
        for row in rows
        for p in row.physical_parts
    ]
    if not priced:
        raise ValueError("retained physical parts are required")
    total.update(
        initial_soc=result.execution.case.initial_soc,
        final_soc=result.execution.final_soc,
        initial_inventory_kwh=10 * result.execution.case.initial_soc,
        final_inventory_kwh=10 * result.execution.final_soc,
        export_duration_s=fsum(p.duration_s for p in pieces if p.grid_kw < -POWER_TOL),
        prohibited_grid_charge_peak_kw=max(
            (p.prohibited_grid_charge_kwh * 3600 / p.duration_s for p in pieces),
            default=0.0,
        ),
        prohibited_grid_charge_duration_s=fsum(
            p.duration_s
            for p in pieces
            if p.prohibited_grid_charge_kwh * 3600 / p.duration_s > POWER_TOL
        ),
        reserve_deficit_kwh_h=fsum(
            10
            * positive_linear_mean(
                p.reserve_target_soc - p.soc_before,
                p.reserve_target_soc - p.soc_after,
            )
            * p.duration_s
            / 3600
            for p in pieces
        ),
        reserve_peak_gap_kwh=max(
            10 * max(0, p.reserve_target_soc - min(p.soc_before, p.soc_after))
            for p in pieces
        ),
        import_cost_cny=fsum(x[0] for x in priced),
        export_revenue_cny=fsum(x[1] for x in priced),
    )
    total["net_cost_cny"] = total["import_cost_cny"] - total["export_revenue_cny"]
    model = BatteryOptimizationModel(10, 0.2, 1, 3, 3, 0.95, 0.95)
    for value in VALUATIONS:
        evidence = DeterministicTerminalEnergyValueCalculator().calculate(
            TerminalEnergyValueInput(result.execution.final_soc, model, value)
        )
        total[f"terminal_value_cny_at_{value}"] = evidence.terminal_energy_value
        total[f"inventory_adjusted_cost_cny_at_{value}"] = (
            total["net_cost_cny"] - evidence.terminal_energy_value
        )
    return total


def metric_tolerance(key: str) -> float:
    if "soc" in key:
        return SOC_TOL
    if key.endswith("_s"):
        return TIME_TOL
    if key.endswith("_kw"):
        return POWER_TOL
    if "cny" in key:
        return DAY_ENERGY_TOL * max(VALUATIONS)
    if key == "reserve_deficit_kwh_h":
        return 10 * SOC_TOL * 24
    return DAY_ENERGY_TOL


def compare_metrics(a: dict[str, float], b: dict[str, float]) -> dict[str, float]:
    if a.keys() != b.keys():
        raise ValueError("metric schemas differ")
    return {key: b[key] - a[key] for key in a}


def run_comparison(output: Path) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=False)
    cases = comparison_cases()
    facts = json.dumps({k: asdict(v) for k, v in cases.items()}, sort_keys=True)
    (output / "inputs.json").write_text(facts, encoding="utf-8")
    records: list[dict[str, object]] = []
    for name, case in cases.items():
        for mode in ("ideal", "dynamic"):
            for identifier in STRATEGIES:
                reference = None
                for step in (3600, 60, 15):
                    result = run_strategy(case, identifier, mode=mode, step_s=step)
                    values = metrics(result)
                    if reference is not None:
                        for key, delta in compare_metrics(reference, values).items():
                            if abs(delta) > metric_tolerance(key):
                                raise AssertionError(
                                    f"step divergence {name}/{identifier}/{key}: "
                                    f"{delta}"
                                )
                    reference = values if reference is None else reference
                    status, reasons = report_status(result)
                    filename = f"{name}-{mode}-{identifier}-{step}.json.gz"
                    with gzip.open(output / filename, "wt", encoding="utf-8") as stream:
                        json.dump(asdict(result), stream, allow_nan=False)
                    records.append(
                        {
                            "case": name,
                            "mode": mode,
                            "strategy": identifier,
                            "physical_step_s": step,
                            "assessment": status,
                            "limitations": reasons,
                            "metrics": values,
                            "excursions": [asdict(x) for x in result.excursions],
                            "findings": [asdict(x) for x in result.findings],
                            "trajectory": filename,
                        }
                    )
    summary: dict[str, object] = {
        "input_sha256": hashlib.sha256(facts.encode()).hexdigest(),
        "records": records,
        "tariff": {
            "currency": "CNY",
            "synthetic": True,
            "import_per_kwh": TARIFF_PROFILE_CNY_PER_KWH,
            "import_source": "ems_simulator/demo.py",
            "export_per_kwh": EXPORT_PRICE,
            "export_source": "ems_simulator/runner.py:TariffSimulationInput",
            "valuation_prices": VALUATIONS,
        },
        "limitations": [
            "Offline synthetic case, not real savings or hardware validation",
            "No degradation, demand, fixed charges or taxes",
            "Terminal value is assigned value, not realized revenue",
            "Dynamic export and grid charge retained; not instantaneous zero export",
            "Complete recomputation from t=0, no pause/resume",
        ],
    }
    (output / "comparison.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    if any(r["assessment"] != "PASS" for r in records):
        raise AssertionError(
            "scenario audit failed or is incomplete; evidence retained"
        )
    (output / "COMPLETE").write_text(
        "all predefined scenario audits passed\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    run_comparison(args.output_dir)


if __name__ == "__main__":
    main()
