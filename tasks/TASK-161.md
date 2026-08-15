# TASK-161 Schedule-Aware vs Economic Schedule-Aware Behavioral Comparison

## 目标

以独立、确定性的 24h 测量 Demo 比较两条既有执行路径：

- TASK-152 `MultiOpportunityExplainableMPCDailySimulationRunner`
- TASK-160 `EconomicMultiOpportunityExplainableMPCDailySimulationRunner`

本任务只读取两条 runner 保留的 outer provenance 和实际 Simulator trace；不改变任何
经济公式、机会窗口、headroom recurrence、候选规划、物理修订、MPC、Feasibility、Actuation
或 Simulator 语义。

## 场景与证据

三组 caller-owned tariff 场景均复用 TASK-154 S4 的有限、非重复双 PV opportunity 物理结构：

- E0：早期 0.20、后续 0.90，预期为 `POSITIVE`，应保留已允许的 cheap-grid charge。
- E1：早期 0.80、后续 0.85，在 0.95 x 0.95 效率后为 `NEGATIVE`，应抑制 cheap-grid charge。
- E2：后续价格等于 `0.80 / (0.95 x 0.95)`，预期为 `BREAK_EVEN`，按 TASK-156 保守策略支持 0 kW。

两个路径在每个场景中共享 exact daily input、forecast horizon tuple、battery model、initial
SOC、objective、strategy descriptor、candidate configuration 和 opportunity configuration；只有
economic gate 存在于 B 路径。比较层不重算 margin 或 reservation：经济证据只从
`EconomicMultiOpportunityMPCCycleResult -> economic_multi_opportunity_optimization_output ->
economic_planning_evidence / candidate_planning_result.economic_value_result` 读取，actual
SOC、battery power、grid power 只从 completed Simulator trace 读取。

## 输出

`python -m ems_simulator.economic_schedule_aware_comparison_demo --output-dir <directory>` 生成：

- `economic_schedule_aware_comparison.csv`：每场景 24 行 A/B 小时证据；无 cheap-grid economic
  value evidence 的字段保持空白。
- `scenario_summary.csv`：实际 Grid/PV/Battery/SOC 和经济 gate 聚合读模型。
- `daily_summary.txt`：对 E0/E1/E2 分开陈述实际观测，不预设“总成本一定更优”。
- `grid_import_cost_by_scenario.svg`、`suppressed_grid_charge_by_scenario.svg`、
  `soc_comparison_e1.svg`、`grid_power_comparison_e1.svg`。

`grid_import_cost` 是只读报告指标：逐小时以
`max(actual_grid_power_kw, 0) * duration_hours * import_price` 汇总。它不反馈到优化，且明确
排除电池衰减、上网收益、辅助功耗、固定费用与不确定性，因此只称为 observed import-cost
delta，不称为总利润。

## 边界

经济证据、候选 gate、实际控制和 observed import cost 是四个不同层次。PV surplus charging
绕过 cheap-grid economic gate；路径差异如在此时段出现，只能来自更早的状态轨迹或下游物理状态，
不是直接的 PV charging 经济抑制。
