# ruff: noqa: E501, RUF001
"""Chinese 24-hour teaching view over the existing residential reference demo."""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Sequence
from dataclasses import dataclass
from html import escape
from io import StringIO
from pathlib import Path

from ems_simulator.economic_ledger import EconomicLedgerInterval
from ems_simulator.economic_multi_opportunity_explainable_mpc_daily import (
    EconomicMultiOpportunityExplainableMPCDailySimulationResult,
    EconomicMultiOpportunityExplainableMPCDailySimulationStepTrace,
)
from ems_simulator.residential_reference_demo import (
    ResidentialReferenceResult,
    run_residential_reference_demo,
)
from optimization import EconomicGridChargeValueResult

SIMULATED_LABEL = "SIMULATED / 虚拟固定输入 / 非真实设备采集"


@dataclass(frozen=True, slots=True)
class DayTeachingResult:
    """Paths and exact source result for one completed teaching export."""

    source_result: ResidentialReferenceResult
    hourly_csv_path: Path
    hourly_json_path: Path
    key_events_path: Path
    summary_path: Path
    linked_curve_path: Path


def run_day_teaching_demo(output_directory: Path) -> DayTeachingResult:
    """Run the established reference once, then render a read-only teaching view."""

    if not isinstance(output_directory, Path):
        raise TypeError("output_directory must be a pathlib.Path")
    output_directory.mkdir(parents=True, exist_ok=True)
    source = run_residential_reference_demo(output_directory / "reference")
    rows = _hourly_rows(source)

    hourly_csv_path = output_directory / "simulated_hourly_decisions_zh.csv"
    hourly_json_path = output_directory / "simulated_hourly_decisions_zh.json"
    key_events_path = output_directory / "simulated_key_events_zh.txt"
    summary_path = output_directory / "simulated_daily_summary_zh.txt"
    linked_curve_path = output_directory / "simulated_linked_day_curve.svg"

    hourly_csv_path.write_text(_csv(rows), encoding="utf-8", newline="")
    hourly_json_path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    key_events_path.write_text(_key_events(rows), encoding="utf-8", newline="")
    summary_path.write_text(_summary(source), encoding="utf-8", newline="")
    linked_curve_path.write_text(_linked_curve(rows), encoding="utf-8", newline="")
    return DayTeachingResult(
        source,
        hourly_csv_path,
        hourly_json_path,
        key_events_path,
        summary_path,
        linked_curve_path,
    )


def _hourly_rows(source: ResidentialReferenceResult) -> list[dict[str, object]]:
    result = source.economic.result
    if not isinstance(
        result, EconomicMultiOpportunityExplainableMPCDailySimulationResult
    ):
        raise TypeError("teaching view requires the existing Economic reference path")
    traces = result.step_traces
    intervals = source.economic.ledger.intervals
    if len(traces) != 24 or len(intervals) != 24:
        raise ValueError("teaching view requires exactly 24 completed hourly facts")
    rows: list[dict[str, object]] = []
    for hour, (trace, interval) in enumerate(zip(traces, intervals, strict=True)):
        rows.append(_hourly_row(hour, trace, interval))
    return rows


def _hourly_row(
    hour: int,
    trace: EconomicMultiOpportunityExplainableMPCDailySimulationStepTrace,
    interval: EconomicLedgerInterval,
) -> dict[str, object]:
    # The ledger interval is produced by the existing typed ledger. Attribute reads
    # stay deliberately local so this wrapper neither rebuilds nor settles economics.
    state = trace.simulation_trace.state
    record = trace.journal_record
    decision = trace.decision_provenance.decision
    feasible = trace.feasible_decision
    actuation = trace.handoff.actuation
    battery_kw = state.battery_result.actual_power_kw
    grid_kw = state.grid_result.actual_grid_power_kw
    planning = trace.economic_multi_opportunity_mpc_cycle_result.economic_multi_opportunity_optimization_output.candidate_planning_result
    economic_value = planning.economic_value_result
    reservation = planning.reservation_result
    explanation = trace.formatted_explanation.text

    timestamp = state.step_identity.timestamp
    if timestamp is None:
        raise ValueError("teaching view requires explicit timestamps")
    return {
        "label": SIMULATED_LABEL,
        "hour": hour,
        "timestamp": timestamp.isoformat(),
        "duration_hours": interval.duration_hours,
        "pv_kw": state.pv_result.actual_power_kw,
        "load_kw": state.load_result.actual_power_kw,
        "import_tariff_cny_per_kwh": state.tariff_result.import_price_cny_per_kwh,
        "strategy": decision.source_strategy.name,
        "candidate_action": record.candidate_action.action,
        "candidate_request_kw_magnitude": record.candidate_requested_power_kw,
        "decision_action": decision.intent.action,
        "decision_request_kw_magnitude": decision.requested_power_kw,
        "approved_action": feasible.approved_intent.action,
        "approved_kw_magnitude": feasible.approved_power_kw,
        "actuation_battery_kw_signed": actuation.battery_power_kw,
        "actual_battery_kw_signed": battery_kw,
        "actual_grid_kw_signed": grid_kw,
        "grid_import_kw": max(grid_kw, 0.0),
        "grid_export_kw": max(-grid_kw, 0.0),
        "soc_before_fraction": interval.soc_before_fraction,
        "soc_after_fraction": interval.soc_after_fraction,
        "physical_revision": record.revision_applied,
        "revision_reasons": list(record.revision_reasons),
        "final_soc_feasible": record.final_soc_feasible,
        "final_power_feasible": record.final_power_feasible,
        "final_horizon_feasible": record.final_battery_horizon_feasible,
        "price_decision_role": _price_role(economic_value),
        "economic_supported_grid_charge_kw": (
            None
            if economic_value is None
            else economic_value.economically_supported_grid_charge_power_kw
        ),
        "headroom_allowed_grid_charge_kw": (
            None if reservation is None else reservation.allowed_grid_charge_power_kw
        ),
        "grid_import_kwh": interval.grid_import_energy_kwh,
        "grid_export_kwh": interval.grid_export_energy_kwh,
        "realized_import_cost_cny": interval.realized_import_cost,
        "realized_export_revenue_cny": interval.realized_export_revenue,
        "battery_degradation_cost_cny": interval.battery_degradation_cost,
        "realized_interval_net_cost_cny": interval.realized_interval_net_cost,
        "decision_explanation_zh": explanation,
        "teaching_explanation_zh": _teaching_explanation(
            record.final_action.action,
            state.pv_result.actual_power_kw,
            state.load_result.actual_power_kw,
            state.tariff_result.import_price_cny_per_kwh,
            battery_kw,
            grid_kw,
            record.revision_reasons,
            economic_value,
        ),
    }


def _price_role(economic_value: EconomicGridChargeValueResult | None) -> str:
    if economic_value is None:
        return "本小时动作绕过低价电网充电经济门；价格仍用于完成后的进口成本核算"
    classification = economic_value.economic_classification.value
    return f"价格参与低价电网充电经济门：{classification}；并用于实际进口成本核算"


def _teaching_explanation(
    action: str,
    pv_kw: float,
    load_kw: float,
    tariff: float,
    battery_kw: float,
    grid_kw: float,
    reasons: tuple[str, ...],
    economic_value: EconomicGridChargeValueResult | None,
) -> str:
    if action == "charge" and pv_kw > load_kw:
        why = "PV 高于家庭负载，现有策略用盈余充电；低价电网充电经济门未参与"
    elif action == "charge" and economic_value is not None:
        supported = economic_value.economically_supported_grid_charge_power_kw
        why = f"无 PV 盈余，现有 Economic 路径按 {tariff:.2f} 元/kWh 评估后支持 {supported:.6f} kW 电网充电"
    elif action == "discharge":
        why = "家庭负载高于 PV，现有路径请求放电降低高价时段购电"
    else:
        why = "现有路径本小时保持 idle；没有可执行的充放电动作"
    constraint = "无物理修订" if not reasons else "物理约束修订：" + "、".join(reasons)
    grid_text = "购电" if grid_kw >= 0.0 else "售电"
    return (
        f"为什么：{why}。约束：{constraint}。结果：电池实际 {battery_kw:+.6f} kW，"
        f"{grid_text} {abs(grid_kw):.6f} kW；均为虚拟仿真事实。"
    )


def _csv(rows: list[dict[str, object]]) -> str:
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: json.dumps(value, ensure_ascii=False)
                if isinstance(value, list)
                else value
                for key, value in row.items()
            }
        )
    return stream.getvalue()


def _key_events(rows: list[dict[str, object]]) -> str:
    selected = {0, 8, 18, 21}
    selected.update(
        _integer(row, "hour") for row in rows if bool(row["physical_revision"])
    )
    lines = [f"{SIMULATED_LABEL}\n", "24 小时关键决策事件\n"]
    for hour in sorted(selected):
        row = rows[hour]
        lines.append(
            f"\n[{row['timestamp']}] {row['decision_action']} "
            f"request={_number(row, 'decision_request_kw_magnitude'):.6f} kW -> "
            f"actuation={_number(row, 'actuation_battery_kw_signed'):+.6f} kW -> "
            f"actual={_number(row, 'actual_battery_kw_signed'):+.6f} kW, "
            f"SOC={_number(row, 'soc_before_fraction'):.2%}->{_number(row, 'soc_after_fraction'):.2%}\n"
            f"{row['teaching_explanation_zh']}\n"
            f"现有中文约束解释：\n{row['decision_explanation_zh']}\n"
        )
    return "".join(lines)


def _summary(source: ResidentialReferenceResult) -> str:
    ledger = source.economic.ledger
    daily = source.economic.result.source_input.daily_mpc_input.integration_input.daily_input
    model = (
        source.economic.result.source_input.daily_mpc_input.battery_optimization_model
    )
    return (
        f"{SIMULATED_LABEL}\n"
        "EOS 虚拟家庭储能 24 小时教学汇总\n"
        "输入来源：复用现有 Residential EMS 1.0 reference fixture 与 Economic runner；24 x 1 小时，perfect forecast。\n"
        f"电池：{model.usable_capacity_kwh:.6f} kWh，初始 SOC={daily.initial_soc:.2%}，"
        f"范围={model.min_soc_fraction:.2%}~{model.max_soc_fraction:.2%}，"
        f"充/放上限={model.max_charge_power_kw:.6f}/{model.max_discharge_power_kw:.6f} kW，"
        f"效率={model.charge_efficiency:.2%}/{model.discharge_efficiency:.2%}。\n"
        f"负载={ledger.total_load_energy_kwh:.6f} kWh，PV={ledger.total_pv_energy_kwh:.6f} kWh，"
        f"购电={ledger.total_grid_import_energy_kwh:.6f} kWh，售电={ledger.total_grid_export_energy_kwh:.6f} kWh，"
        f"电池吞吐={ledger.total_battery_throughput_kwh:.6f} kWh，最终 SOC={ledger.final_soc_fraction:.2%}。\n"
        f"实际进口成本={ledger.total_realized_import_cost:.6f}，出口收益={ledger.total_realized_export_revenue:.6f}，"
        f"退化成本={ledger.total_battery_degradation_cost:.6f}，实际净成本={ledger.total_realized_net_cost:.6f}。\n"
        "价格口径：低价无 PV 盈余时参与 Economic 电网充电 gate；每小时进口价也用于完成后的实际成本核算。"
        "出口价 0.20、退化费率 0.05、终端估值 0.85 均为既有 demo 会计假设，不代表真实合同或优化收益。\n"
        "边界：仅模拟；不是设备命令、PCS/BMS/HIL、现场控制或预测误差鲁棒性证据。\n"
    )


def _linked_curve(rows: list[dict[str, object]]) -> str:
    power_series = (
        ("PV", "pv_kw", "#f2a900"),
        ("家庭负载", "load_kw", "#d62728"),
        ("电池(+充/-放)", "actual_battery_kw_signed", "#2ca02c"),
        ("购电", "grid_import_kw", "#1f77b4"),
        ("售电", "grid_export_kw", "#9467bd"),
    )
    all_power = [_number(row, key) for _, key, _ in power_series for row in rows]
    lower, upper = min(-3.0, min(all_power)), max(3.0, max(all_power))
    power_paths = "".join(
        _polyline(rows, key, color, 70.0, 310.0, lower, upper)
        for _, key, color in power_series
    )
    legends = "".join(
        f'<line x1="{65 + index * 155}" y1="342" x2="{88 + index * 155}" y2="342" stroke="{color}" stroke-width="3"/>'
        f'<text x="{92 + index * 155}" y="347" font-size="12">{escape(name)}</text>'
        for index, (name, _, color) in enumerate(power_series)
    )
    soc_points = " ".join(
        f"{_x(index):.1f},{_soc_y(_number(row, 'soc_after_fraction')):.1f}"
        for index, row in enumerate(rows)
    )
    hour_labels = "".join(
        f'<text x="{_x(hour) - 8:.1f}" y="565" font-size="11">{hour:02d}</text>'
        for hour in range(0, 24, 3)
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="980" height="610" viewBox="0 0 980 610">'
        '<rect width="980" height="610" fill="white"/>'
        '<text x="38" y="32" font-size="21" font-weight="bold">SIMULATED 虚拟家庭储能 24 小时联动曲线</text>'
        '<text x="38" y="52" font-size="12" fill="#555">固定输入、非真实采集；所有曲线共用 00–23 小时时间轴</text>'
        '<text x="20" y="78" font-size="12">功率 kW</text>'
        f'<line x1="55" y1="{_power_y(0.0, lower, upper):.1f}" x2="950" y2="{_power_y(0.0, lower, upper):.1f}" stroke="#888"/>'
        f"{power_paths}{legends}"
        '<text x="20" y="390" font-size="12">SOC</text>'
        '<line x1="55" y1="520" x2="950" y2="520" stroke="#aaa"/>'
        '<line x1="55" y1="390" x2="950" y2="390" stroke="#ddd"/>'
        f'<polyline fill="none" stroke="#00838f" stroke-width="3" points="{soc_points}"/>'
        '<text x="62" y="410" font-size="11" fill="#00838f">100%</text>'
        '<text x="62" y="516" font-size="11" fill="#00838f">20%</text>'
        f"{hour_labels}"
        '<text x="455" y="590" font-size="12">小时 (UTC)</text>'
        "</svg>\n"
    )


def _polyline(
    rows: list[dict[str, object]],
    key: str,
    color: str,
    top: float,
    bottom: float,
    lower: float,
    upper: float,
) -> str:
    points = " ".join(
        f"{_x(index):.1f},{top + (upper - _number(row, key)) / (upper - lower) * (bottom - top):.1f}"
        for index, row in enumerate(rows)
    )
    return (
        f'<polyline fill="none" stroke="{color}" stroke-width="2.4" points="{points}"/>'
    )


def _power_y(value: float, lower: float, upper: float) -> float:
    return 70.0 + (upper - value) / (upper - lower) * 240.0


def _soc_y(value: float) -> float:
    return 520.0 - (value - 0.20) / (1.0 - 0.20) * 130.0


def _x(hour: int) -> float:
    return 65.0 + hour * (875.0 / 23.0)


def _number(row: dict[str, object], key: str) -> float:
    value = row[key]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{key} must be numeric")
    return float(value)


def _integer(row: dict[str, object], key: str) -> int:
    value = row[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be an integer")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="EOS simulated 24-hour household-storage teaching example"
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args(argv)
    result = run_day_teaching_demo(arguments.output_dir)
    print(SIMULATED_LABEL)
    for path in (
        result.hourly_csv_path,
        result.hourly_json_path,
        result.key_events_path,
        result.summary_path,
        result.linked_curve_path,
    ):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
