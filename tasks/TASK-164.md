# TASK-164 Terminal-Value-Adjusted Economic Behavior Re-evaluation

## 目标

TASK-164 对 TASK-161 已冻结的 E0 Positive、E1 Negative、E2 Break-even 场景做 post-run accounting
re-evaluation。它运行完全相同的 Schedule-aware 与 Economic Schedule-aware 已有路径，然后以实际
Simulator terminal SOC 生成 TASK-162 `TerminalEnergyValueEvidence`，并以 TASK-161 已观察到的
`grid_import_cost` 生成 TASK-163 `EconomicOutcomeEvidence`。

```text
net_economic_cost = realized_import_cost - terminal_energy_value
```

## 终端估值规则

每个场景使用其 exact TASK-161 tariff profile 中的最高 import price 作为 caller-selected terminal
valuation price；同一场景的 Schedule 与 Economic 路径严格使用同一个数值。TASK-162 不选择价格，
TASK-164 也不按路径选择价格。

## 已观察结论

- E0：实际控制、terminal SOC、terminal value 和 net economic cost 均相同，因此 positive economics
  不会无谓抑制既有 headroom-allowed charge。
- E1、E2：两条路径都以实际 `SOC=1.0` 结束，故在同一 battery model/valuation price 下 terminal value
  相同；TASK-161 已观察到的 `-0.817950` Economic minus Schedule import-cost delta 原样成为 net-cost
  delta。终端价值没有改变这两个 fixture 的结论。

生成 `terminal_value_economic_summary.csv`、`evaluation_summary.txt` 和三张 stable SVG，另保留
TASK-161 exact path results、terminal value evidence 和 outcome evidence。该评估不改变 TASK-155 至
TASK-161 的策略、规划、MPC、Feasibility、Actuation 或 Simulator。

## Accounting boundary

这是 limited accounting：已实现 import cost 减已赋值的 terminal stored-energy value，不是完整 profit。
它不含 export revenue、degradation、auxiliary consumption、fixed/demand charges、tax、uncertainty、
forecast error、capital cost 或其他 opportunity cost。
