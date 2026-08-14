# TASK-153 Full vs Rolling vs Schedule-Aware Behavioral Demo

## 目标

在 TASK-146 的有限、非重复、24 小时双 PV 机会诊断场景上，对比三条已经存在的
应用路径：full-horizon headroom、rolling first-opportunity headroom，以及
multi-opportunity schedule-aware headroom。TASK-153 是测量和行为验证任务；它不新增
优化、预约或物理修正算法。

## 场景与路径

- 场景复用 TASK-146：PV 机会 #1 为 08:00--10:00，11:00--13:00 为真实非盈余间隙，
  PV 机会 #2 为 14:00--17:00，gap tolerance 为 1。
- 三条路径复用相同的 caller-owned 日输入、24 个有限 forecast horizons、初始 SOC、
  电池模型、MPC 配置、目标和 strategy descriptor。
- Full 使用既有 TASK-138 日 runner；Rolling 使用 TASK-144 runner；Schedule-aware
  使用 TASK-152 runner。
- 每条路径都只把上一个 Simulator trace 的实际 `next_state.soc` 与实际 grid result
  反馈给下一小时；预测 SOC、headroom target 和 candidate 从不被当成实际状态。

## 观测与 provenance

新 CLI 为：

```text
python -m ems_simulator.schedule_aware_headroom_comparison_demo \
  --output-dir simulation_output_task153_schedule_aware
```

它只读取既有 outer-cycle evidence。Schedule-aware 行严格从：

`MultiOpportunityMPCCycleResult -> multi_opportunity_optimization_output ->
headroom_schedule -> entries[0] -> reservation_result -> physical_output`

导航，不会依据 PV/Load profile 重算 schedule、depletion 或 reservation。Rolling 与 Full
也只读取各自 outer runner 的原始 evidence。

输出包括对比 CSV、recommended target、required headroom、actual SOC、actual grid power
四张 SVG，以及 `daily_summary.txt`。CSV 对无 opportunity 的时段保持空证据字段。

## 实测结果

00:00 的 evidence：

- Full：required headroom `8.000000 kWh`、target SOC `0.200000`、cheap-grid allowance
  `0.000000 kW`。
- Rolling：first opportunity `08:00--10:00`、required headroom `3.800000 kWh`、target
  SOC `0.620000`、allowance `1.263158 kW`。
- Schedule-aware：2 个机会，首条 standalone headroom `3.800000 kWh`、schedule-adjusted
  headroom `8.000000 kWh`、gap load energy `2.400000 kWh`、stored depletion potential
  `2.526316 kWh`、target SOC `0.200000`、allowance `0.000000 kW`。

日级结果：

| 路径 | Grid import (kWh) | Grid export (kWh) | 吸收 PV 盈余 (kWh) | Final SOC |
| --- | ---: | ---: | ---: | ---: |
| Full | 12.100000 | 7.536842 | 5.263158 | 0.200000 |
| Rolling | 13.363158 | 8.800000 | 4.000000 | 0.200000 |
| Schedule-aware | 12.100000 | 7.536842 | 5.263158 | 0.200000 |

在该 fixture 中，schedule-aware 保留了后续机会所需的 headroom，避免了 TASK-146 rolling
路径在 00:00 额外充入 `1.263158 kWh` 后造成的同等 PV 吸收损失；其实际控制结果与 Full
一致。该结果是观察结论，不代表 schedule-aware 在所有场景中最优。

`Schedule-aware is not assumed to be optimal; this demo reports observed behavior.`

## 非目标

不修改 TASK-132/147 的 accounting、不修改 TASK-148 reservation、不增加 proactive discharge、
future price weighting、terminal SOC、Zero Export、求解器、Runtime 或 Scheduler；也不修改
TASK-139、TASK-145 和 TASK-146 的既有 demo。
