# TASK-146 Multi-Opportunity Rolling Headroom Behavioral Validation

## 目标

以一个有限、非重复的 24 小时诊断场景，比较既有 full-horizon 与 rolling-opportunity headroom accounting。任务只复用 TASK-138 和 TASK-144 runner，既不修改 TASK-132/133/140/141 公式和 selector，也不新增控制逻辑。

实验问题是：在两段被真实非-surplus gap 分隔的 PV surplus 存在时，rolling 是否只为下一段机会保留 headroom；这种 accounting 差异是否进一步影响 reservation、SOC、grid 和 PV absorption。

## 场景

- 电池：10 kWh，充/放电上限 3 kW，效率 95%，SOC 20%–100%，初始 SOC 50%。
- 00:00–05:00：PV 0 kW、Load 0.8 kW、低价 0.20 CNY/kWh。
- 第一 PV 机会 08:00–10:00：`PV/Load = 2.0/0.8, 2.5/0.8, 2.0/0.9 kW`，surplus 为 1.2、1.7、1.1 kW。
- 间隔 11:00–13:00：`PV <= Load`，分别为 `0.4/1.0, 0.2/1.1, 0.1/1.0 kW`，没有正 surplus。
- 第二 PV 机会 14:00–17:00：`PV/Load = 3.0/1.0, 4.0/1.0, 3.5/1.0, 2.5/1.2 kW`，surplus 为 2.0、3.0、2.5、1.3 kW。
- 18:00 后为 evening deficit；18:00–21:00使用高价 0.90 CNY/kWh。
- `PVOpportunityWindowConfiguration(max_inactive_gap_points=1)`；三小时 gap 必然分隔两个 window。

每小时显式提供一个 24-point ForecastHorizon：先放入该小时至 23:00 的剩余日内事实，再加入 caller-owned 的 0 PV / 0 Load / 0.50 price tail。tail 仅满足既有固定 horizon contract，绝不重复第二天曲线或引入虚构 PV opportunity。

## 输出与 provenance

CLI：

```text
python -m ems_simulator.multi_opportunity_headroom_demo --output-dir simulation_output_task146_multi_opportunity
```

输出 `multi_opportunity_headroom_comparison.csv`、`daily_summary.txt` 和四张 SVG。rolling 字段直接沿用：

```text
RollingHeadroomAwareMPCCycleResult
→ rolling_headroom_optimization_output
→ rolling_headroom_requirement
→ opportunity_window / selected_forecast_horizon / headroom_requirement
```

full 字段则直接读取 TASK-137 outer result 的 full-horizon headroom evidence。PV absorption 为读取真实 simulator trace 的估算值：每小时 `min(max(actual_battery_charge, 0), max(PV - Load, 0)) × duration`；不改变 simulator contract。

## 实测结果

00:00 的 accounting 与 reservation 确实分离：

| 指标 | Full | Rolling |
| --- | ---: | ---: |
| Required headroom | 8.000000 kWh | 3.800000 kWh |
| Recommended max SOC | 20.00% | 62.00% |
| Requested cheap-grid charge | 3.000000 kW | 3.000000 kW |
| Allowed cheap-grid charge | 0.000000 kW | 1.263158 kW |

rolling 在 cycle 0–10 选择第一机会 08:00–10:00；cycle 11 转向第二机会 14:00–17:00；cycle 18–23 没有 opportunity，共 6 个 no-opportunity cycles。selected window 随 forecast 缩短共出现 15 个 distinct index interval，这是同一机会残余切片与第二机会的实际 provenance，而非 selector 的重算或合并。

| 指标 | Full | Rolling | Rolling − Full |
| --- | ---: | ---: | ---: |
| Grid import | 12.100000 kWh | 13.363158 kWh | +1.263158 |
| Grid export | 7.536842 kWh | 8.800000 kWh | +1.263158 |
| Battery throughput | 12.863158 kWh | 12.863158 kWh | 0 |
| Final SOC | 20% | 20% | 0 |
| Charge / Discharge / Idle | 4 / 4 / 16 | 4 / 4 / 16 | — |
| Revised / SOC-limited / power-limited | 5 / 5 / 0 | 5 / 5 / 0 | — |
| Reduced / zeroed reservations | 6 / 6 | 6 / 5 | — |
| Estimated absorbed PV surplus | 5.263158 kWh | 4.000000 kWh | −1.263158 |

## 结论与限制

Accounting effect：存在。full 在 00:00 同时为两段机会计算 8.0 kWh headroom；rolling 只为第一段计算 3.8 kWh，并给出更高的 62% target。

Reservation effect：存在。rolling 在 00:00 允许 1.263158 kW cheap-grid charge，full 为 0。

Control effect：存在，但不是收益。rolling 的额外低价充电使其在第一机会后先达到 100% SOC；14:00 full 仍实际充电 1.263158 kW、grid export 为 0.736842 kW，而 rolling 因 max SOC 实际充电 0 kW、grid export 为 2.0 kW。故该场景下 rolling 的 grid import 和 export 都增加，且估算 PV surplus absorption 更低。

This scenario is intentionally diagnostic and is not claimed to represent a universal household profile.

该任务证明了 separated finite opportunities 会造成 early accounting、reservation 与 control divergence，但不证明 rolling universally better。其限制是没有 proactive headroom creation、terminal SOC、future load reservation 或 export economics；这些能力仍不属于本 TASK。
