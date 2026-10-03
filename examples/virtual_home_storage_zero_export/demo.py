# ruff: noqa: E501, RUF001
"""Generate a simulation-only S09 Zero Export opt-in correction report."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from io import StringIO
from pathlib import Path

from ems_simulator.battery import SimpleBatteryPhysicsModel
from ems_simulator.economic_schedule_aware_comparison_demo import (
    _economic_runner,
    _schedule_runner,
)
from ems_simulator.input import BatteryParameters
from ems_strategy import ZeroExportFeasibility
from examples.virtual_home_storage_defect_campaign.campaign import (
    CONFIGURATION,
    _inputs,
    executable_scenarios,
    run_campaign,
)
from examples.virtual_home_storage_zero_export.correction import (
    OptInZeroExportStepExecutor,
)

SIMULATED_LABEL = "SIMULATED / 显式 opt-in 弃光 / 非设备遥测"


@dataclass(frozen=True, slots=True)
class S09OptInRow:
    evidence_kind: str
    telemetry: bool
    strategy: str
    default_pv_available_kw: float
    default_pv_actual_kw: float
    default_battery_actual_kw: float
    default_grid_actual_kw: float
    opt_in_status: str
    opt_in_reason: str
    opt_in_pv_utilized_kw: float
    opt_in_pv_curtailed_kw: float
    opt_in_grid_power_kw: float
    opt_in_pv_curtailed_kwh: float
    opt_in_grid_energy_kwh: float
    battery_action_unchanged: bool
    source_pv_input_unchanged: bool


@dataclass(frozen=True, slots=True)
class ZeroExportOptInDemoResult:
    rows: tuple[S09OptInRow, ...]
    output_paths: tuple[Path, ...]


def run_demo(output_directory: Path) -> ZeroExportOptInDemoResult:
    """Replay default evidence, then explicitly opt in for S09 h0 only."""
    if not isinstance(output_directory, Path):
        raise TypeError("output_directory must be a pathlib.Path")
    output_directory.mkdir(parents=True, exist_ok=True)
    baseline = run_campaign(output_directory / "default_campaign")
    spec = next(
        item
        for item in executable_scenarios()
        if item.scenario_id == "S09_ZERO_EXPORT_FULL"
    )
    schedule_input, economic_input = _inputs(spec, output_directory / "s09")
    trajectories = (
        ("Schedule", _schedule_runner(CONFIGURATION).run(schedule_input)),
        ("Economic", _economic_runner(CONFIGURATION).run(economic_input)),
    )
    model = spec.battery_model
    parameters = BatteryParameters(
        model.usable_capacity_kwh,
        model.max_charge_power_kw,
        model.max_discharge_power_kw,
        model.charge_efficiency,
        model.discharge_efficiency,
        model.min_soc_fraction,
    )
    rows: list[S09OptInRow] = []
    for strategy, trajectory in trajectories:
        trace = trajectory.step_traces[0]
        original = trace.simulation_trace
        source_battery_power = original.state.battery_result.actual_power_kw
        correction = OptInZeroExportStepExecutor.execute(
            original.simulation_input,
            zero_export_feasibility=ZeroExportFeasibility(
                trace.decision_provenance.decision,
                trace.decision_provenance,
                False,
            ),
            expected_provenance=trace.decision_provenance,
            source_handoff=trace.handoff,
            battery_model=SimpleBatteryPhysicsModel(parameters),
            export_limit_kw=0.0,
            curtailment_allowed=True,
        )
        if correction.simulation_trace is None:
            raise AssertionError("authorized S09 correction must produce a trace")
        evidence = correction.correction.evidence
        state = correction.simulation_trace.state
        if (
            evidence.pv_utilized_kw is None
            or evidence.pv_curtailed_kw is None
            or evidence.resulting_grid_power_kw is None
            or evidence.pv_curtailed_energy_kwh is None
            or evidence.resulting_grid_energy_kwh is None
        ):
            raise AssertionError("satisfied correction must contain output values")
        rows.append(
            S09OptInRow(
                "SIMULATED",
                False,
                strategy,
                original.simulation_input.pv_input.available_power_kw,
                original.state.pv_result.actual_power_kw,
                source_battery_power,
                original.state.grid_result.actual_grid_power_kw,
                evidence.status,
                evidence.reason_code,
                evidence.pv_utilized_kw,
                evidence.pv_curtailed_kw,
                evidence.resulting_grid_power_kw,
                evidence.pv_curtailed_energy_kwh,
                evidence.resulting_grid_energy_kwh,
                state.battery_result.actual_power_kw == source_battery_power,
                state.pv_result.simulation_input is original.simulation_input.pv_input,
            )
        )

    limitation_counts = Counter(
        item.finding_code
        for item in baseline.path_results
        if item.status == "LIMITATION"
    )
    output_rows = [asdict(row) for row in rows]
    json_path = output_directory / "simulated_zero_export_opt_in.json"
    csv_path = output_directory / "simulated_zero_export_opt_in.csv"
    report_path = output_directory / "simulated_zero_export_opt_in_report_zh.md"
    json_path.write_text(
        json.dumps(output_rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    csv_path.write_text(_csv(output_rows), encoding="utf-8", newline="")
    report_path.write_text(
        _report(tuple(rows), limitation_counts), encoding="utf-8", newline=""
    )
    return ZeroExportOptInDemoResult(
        tuple(rows),
        (json_path, csv_path, report_path),
    )


def _csv(rows: list[dict[str, object]]) -> str:
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def _report(rows: tuple[S09OptInRow, ...], limitations: Counter[str]) -> str:
    lines = [
        f"# {SIMULATED_LABEL}\n",
        "## S09 显式 opt-in 结果\n",
        "默认 runner 保持未修正证据：PV actual=10 kW、battery actual=0 kW、grid=-10 kW。"
        " 本报告没有覆盖或重写该历史 trace。\n",
    ]
    for row in rows:
        lines.append(
            f"- {row.strategy}: `{row.opt_in_status}/{row.opt_in_reason}`，"
            f"PV available={row.default_pv_available_kw:.6f} kW，"
            f"utilized={row.opt_in_pv_utilized_kw:.6f} kW，"
            f"curtailed={row.opt_in_pv_curtailed_kw:.6f} kW，"
            f"battery={row.default_battery_actual_kw:.6f} kW，"
            f"grid={row.opt_in_grid_power_kw:.6f} kW；"
            f"curtailed energy={row.opt_in_pv_curtailed_kwh:.6f} kWh，"
            f"grid energy={row.opt_in_grid_energy_kwh:.6f} kWh。\n"
        )
    lines.extend(
        (
            "## 默认 Campaign 限制保持\n",
            "默认未 opt-in Campaign 仍为 PASS=24、LIMITATION=8、FAIL=0、"
            "REJECTED_AS_EXPECTED=3。以下限制没有被本示例改写：\n",
        )
    )
    for code, count in sorted(limitations.items()):
        lines.append(f"- `{code}`: {count} 条默认路径。\n")
    lines.extend(
        (
            "## 边界\n",
            "- correction-only 输出只表示一个虚拟单步在显式弃光授权下可以满足零上网。\n",
            "- 没有改变策略 action、Battery actual、默认 runner、套利或 forecast guard。\n",
            "- PV、Load、Battery 和 Grid 都使用现有 Simulator 的同一 kW 功率边界；"
            "没有推断真实 AC/DC 拓扑、变流损耗、设备 ACK 或现场执行。\n",
        )
    )
    return "".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="EOS simulation-only opt-in Zero Export curtailment lesson"
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    arguments = parser.parse_args(argv)
    result = run_demo(arguments.output_dir)
    print(SIMULATED_LABEL)
    for path in result.output_paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
