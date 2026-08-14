# TASK-145 Full Headroom vs Rolling Headroom 24h Demo

## 目标

在同一组 TASK-139 canonical 24 小时场景、初始 SOC、电池参数、tariff 与 24-point repeating perfect forecast 下，运行并观测两条既有路径：

- TASK-138 / TASK-139 的 full-horizon headroom daily runner；
- TASK-144 的 rolling-opportunity headroom daily runner。

本任务是比较与导出，不改变优化、headroom、物理修正、Feasibility、Actuation 或 Simulator 语义。

## 实现

新增 `ems_simulator/rolling_headroom_mpc_demo.py`，提供：

- `python -m ems_simulator.rolling_headroom_mpc_demo --output-dir <dir>`；
- 两条 runner 的 24 个 caller-owned cycle；
- `headroom_comparison.csv`：每小时保留 entering SOC、full/rolling headroom、reservation、candidate、physical-final 与实际 battery/grid/SOC 结果；
- `recommended_soc_target.svg`、`soc_comparison.svg`、`grid_power_comparison.svg`；
- 含 delta 与 reservation 计数的 `daily_summary.txt`。

full 输出直接读取 TASK-137 outer result；rolling 输出直接读取 TASK-143 outer result 的 exact `rolling_headroom_optimization_output`。rolling window 的 source point/index 由既有 TASK-141 provenance 给出，未从结果曲线反推。

## 实测结果

执行：

```text
python -m ems_simulator.rolling_headroom_mpc_demo --output-dir simulation_output_task145_rolling_headroom
```

在当前 canonical 24-point repeating-day forecast 中，两个路径观测到的结果相同：

| 指标 | Full horizon | Rolling opportunity | Rolling - Full |
| --- | ---: | ---: | ---: |
| Grid import (kWh) | 11.200000 | 11.200000 | 0.000000 |
| Grid export (kWh) | 23.736842 | 23.736842 | 0.000000 |
| Battery throughput (kWh) | 12.863158 | 12.863158 | 0.000000 |
| Final SOC | 20.00% | 20.00% | 0.00% |
| Charge / Discharge / Idle | 3 / 5 / 16 | 3 / 5 / 16 | — |
| Revised decisions | 9 | 9 | 0 |
| SOC-limited / power-limited | 9 / 5 | 9 / 5 | 0 / 0 |
| Grid-charge reservations | 6 reduced / 6 zeroed | 6 reduced / 6 zeroed | 0 / 0 |

两条路径的最大 required headroom 都是 8.0 kWh、最小 recommended pre-PV max SOC 都是 20%。rolling 路径每小时都选到 opportunity；其 source-index 窗口随 caller horizon 滚动，共观察到 24 个不同的 index interval，但每个窗口的有效 PV-surplus accounting 与 full path 在该 repeating-day 输入下等价。

## 结论与限制

Rolling is not automatically better; this demo reports observed behavior.

本 demo 没有证明 rolling accounting 在任何输入上都更少保守，也没有观察到控制收益。当前 rolling selector 只选取“下一段连续 PV opportunity”；canonical forecast 的第一个机会包含同一日完整可见 surplus 段，因此它没有缩短 TASK-132 的 headroom accounting。后续应使用含多个分离机会、不同 cloud gap、或非重复预测的场景，继续验证选择窗缩短时的 accounting 与控制差异。
