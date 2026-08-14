# TASK-154 Schedule-Aware Multi-Scenario Behavioral Evaluation

## 目标

以确定性的有限 24 小时场景矩阵，观测既有 Full-horizon、Rolling first-opportunity 与
Multi-opportunity schedule-aware 三条路径的行为敏感性。任务只复用 TASK-153 的三路径执行、
指标与 PV 盈余吸收读模型；不改变 schedule recurrence、reservation、optimization、MPC 或
Simulator。

## 场景矩阵

- S0：TASK-153/TASK-146 基线，initial SOC 50%。
- S1/S2：分别增大/减小两个 PV 机会之间的真实净负载缺口。
- S3：把低价 tariff 延长到上午，以检验动态 target 放宽是否会影响 reservation。
- S4/S5：分别缩小/扩大第二个 PV 机会。
- S6/S7：基线 forecast 与 tariff 下的 initial SOC 20%/80%。
- S8 的中等 SOC 分组由 S0 表示，不重复运行相同事实。

每个 scenario 均保留 caller-owned 24-point finite horizons；尾部是显式零盈余事实而不是次日
profile 重复。每条路径仍以实际上一小时 Simulator SOC 与 grid result 作为下一小时事实。

## 结果与分类

三种 deterministic 分类分别针对 early target、early allowance 和日级 control vector
（import/export、PV absorption、throughput、final SOC）：`FULL_LIKE`、`ROLLING_LIKE`、
`INTERMEDIATE` 与 `DISTINCT`。分类只描述本次观测，不表示策略优劣。

实测结果：

- S0、S2、S3、S5、S6、S7 为 Full-like；S1 为 Rolling-like；S4 是 target、allowance 与
  control 均为 Intermediate 的有效中间案例。
- S1 的 depletion potential 为 `8.736842 kWh`，足以使 schedule 的 early adjusted
  headroom 降至 first-opportunity standalone `3.800000 kWh`；因此其 early allowance 与
  Rolling 都为 `1.263158 kW`。这也暴露了一个 failure mode：自然缺口很大时，局部允许
  cheap-grid charging 仍可能像 Rolling 一样减少后续 PV absorption。
- S2 的 depletion potential 仅 `0.842105 kWh`，schedule 保持 Full-like。
- S4 中 schedule adjusted headroom 为 `4.028684 kWh`，target `59.7132%`，allowance
  `1.022438 kW`，介于 Full 与 Rolling 之间；其 PV absorption `4.240720 kWh` 也处于
  两者之间。
- S3 第一次 target divergence 在 10:00，tariff 仍为 `0.20`，但当前为 PV-surplus charge，
  因此没有 cheap-grid reservation。延长低价窗口并未产生新的控制收益。
- 高 initial SOC（S7）使三条路径都没有 early grid allowance，accounting 差异被当前 SOC
  遮蔽；低 initial SOC（S6）放大了 Rolling 的额外充电与 PV absorption 损失。

## 输出

```text
python -m ems_simulator.schedule_aware_multiscenario_evaluation \
  --output-dir simulation_output_task154_multiscenario
```

输出根目录包含 `scenario_summary.csv`、`evaluation_summary.txt` 与四张 cross-scenario SVG。
每个 `S0`--`S7` 子目录保留 TASK-153 形状的 24 行三路径比较 CSV 与路径级诊断工件。

## 非目标

不实现新的 schedule 算法、tariff-aware schedule、主动预放电、terminal SOC、Zero Export、
求解器、Runtime 或 Scheduler。该矩阵是确定性诊断样本，不是家庭总体的统计性结论。
