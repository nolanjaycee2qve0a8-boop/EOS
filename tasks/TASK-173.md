# TASK-173 — Daily / Interval Economic Ledger

## 目标

TASK-173 在已经完成的 24h Simulator 实际轨迹之上建立可审计的逐时经济账本。
它只读取完成后的 `SimulationExecutionTrace`：不会再次运行策略、候选规划、物理修正、MPC、
Feasibility、Actuation 或 Simulator。

## 账本边界

```text
completed daily trajectory
  -> EconomicLedgerInput
  -> interval Import / Export / Degradation evidence
  -> DailyEconomicLedger
  -> one TerminalEnergyValueEvidence
  -> one ExtendedEconomicOutcomeEvidence
```

每一条 `EconomicLedgerInterval` 都保留已经实现的能量、费率与 TASK-169/170/171
evidence。全天 `DailyEconomicLedger` 汇总逐时结果；终端价值只在全天末尾作为一次
credit，绝不分摊到常规区间。

## 已冻结公式与符号

Simulator 约定被显式读取而不被重新解释：

```text
positive actual grid power -> import
negative actual grid power -> export

grid_import_energy = max(actual_grid_power_kw, 0) * duration_hours
grid_export_energy = max(-actual_grid_power_kw, 0) * duration_hours
battery_throughput = abs(actual_battery_power_kw) * duration_hours

realized_interval_net_cost =
    realized_import_cost
    - realized_export_revenue
    + battery_degradation_cost
```

全天最终汇总仍只使用 TASK-168：

```text
adjusted_net_economic_cost =
    total_realized_import_cost
    - total_realized_export_revenue
    + total_battery_degradation_cost
    - terminal_energy_value
```

较低的成本在此有限会计模型下更优；负的 adjusted cost 不等于已经实现的现金利润。

## 责任与复用

- TASK-171：每个 interval 使用该 interval 的实际 import 能量与实际 import tariff。
- TASK-169：每个 interval 使用已实现 export 能量和 caller-supplied export tariff。
- TASK-170：每个 interval 使用实际电池功率绝对值形成的 throughput 与 caller-supplied rate。
- TASK-162：只在全天末尾，对实际 final SOC 计算一次终端能量价值。
- TASK-168：只对每日 totals 聚合一次，不重新计算任何原子 evidence。

账本输入保持 exact completed trajectory 与 exact `BatteryOptimizationModel` identity。
它不以模拟投影 SOC 替代实际 Simulator SOC，也不以平均价替代逐时 TOU 实际价格。

## 可运行参考

```powershell
python -m ems_simulator.economic_ledger `
  --output-dir simulation_output_task173_economic_ledger
```

参考路径复用 TASK-165 已定义的固定 Schedule-aware trajectory，生成：

- `economic_ledger_intervals.csv`
- `economic_ledger_daily_summary.csv`
- `economic_ledger_summary.txt`

生成输出不纳入版本控制。TASK-173 是观察/结算层，不是新的控制目标、结算系统或财务收益声明。
