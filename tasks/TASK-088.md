# TASK-088 — Simulation Result CSV Export and Visualization

## 目标

将 completed `DailySimulationResult` 转换为工程可读、确定性的 CSV、SVG 和 daily
energy summary，同时保持 simulation evidence 不可变。

## 输入与输出

输入是 exact `DailySimulationResult`。`SimulationResultExporter.export()` 返回 frozen、
slotted `DailySimulationExport`，其中包含：

- `csv_content`；
- `DailyEnergySummary`；
- `SimulationVisualization`，包含 power curve SVG 与 SOC curve SVG。

所有 output artifacts 保存 exact source result reference。Exporter 只读取 trace evidence，
不修改、复制、重建或重新执行 simulation。

## CSV contract

CSV 固定包含 24 个 caller-ordered rows 和以下列：

```text
timestamp
pv_power_kw
load_power_kw
battery_power_kw
grid_power_kw
soc
```

Timestamp 使用 exact step identity 中 timezone-aware datetime 的 ISO 8601 表达。所有功率
与 SOC 来自对应 trace 的 realized state。输出使用固定列顺序和 `\n` 换行，因此相同 result
产生完全相同的 CSV content。

## Visualization contract

- `power_curve.svg` 同时绘制 PV、Load、Battery 与 Grid power。
- `soc_curve.svg` 绘制每一步完成后的 Battery SOC。
- SVG 仅使用 Python 标准库与 deterministic coordinate calculation。
- 不引入 dashboard、browser、plotting runtime、telemetry 或 third-party graphics state。

## Daily summary

所有 energy 单位为 raw kWh，并使用每一步显式 duration 积分：

- PV energy；
- Load energy；
- Battery throughput：`sum(abs(actual_battery_power) * duration)`；
- Grid import energy：Grid power 正值部分；
- Grid export energy：Grid power负值部分的正 magnitude。

## File export

`write_files()` 只写入 caller 提供的 existing directory，并使用固定文件名：

- `simulation_result.csv`；
- `power_curve.svg`；
- `soc_curve.svg`。

它不创建数据库、远程服务、Runtime storage 或 hidden history。

## Non-goals

- 不实现 database、dashboard、Web API、cloud 或 real-time monitoring。
- 不引入 Runtime、Scheduler、Device 或 Command。
- 不修改 Phase 5、Phase 6 或 Phase 7 contracts。
- 不重新运行 models、runner、strategy 或 constraints。

## Validation

- CSV content、header、timestamp order、power 与 SOC values；
- deterministic repeated output；
- valid Power/SOC SVG documents；
- daily energy integration 与 Grid import/export separation；
- immutable source identity 与 output artifacts；
- exact file contents；
- full pytest、Ruff、mypy 与 pre-commit。
