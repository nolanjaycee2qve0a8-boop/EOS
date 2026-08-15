# TASK-162 Terminal Stored-Energy Value Evidence

## 目标

TASK-161 的 observed import-cost 比较表明：两个路径在 horizon 终点保有不同 SOC 时，仅比较已实现
购电成本并不完整。TASK-162 因此增加独立、纯粹的终端储能价值 evidence；它不做优化，也不改变
任何实际控制。

## Public contracts

- `TerminalEnergyValueInput`
- `TerminalEnergyValueEvidence`
- `TerminalEnergyValueBoundary`
- `DeterministicTerminalEnergyValueCalculator`

输入只包含已知 `terminal_soc`、exact `BatteryOptimizationModel` 和 caller-supplied
`valuation_import_price`。模块不读取 forecast、schedule、reservation、candidate、EMSDecision 或
Simulator trace，也不选择“正确”的 valuation price。

## 已冻结语义

可用 energy floor 复用 `BatteryOptimizationModel.min_soc_fraction`，不创建新的 reserve 概念：

```text
usable_soc_fraction = max(terminal_soc - min_soc_fraction, 0)
usable_terminal_stored_energy_kwh = usable_soc_fraction * usable_capacity_kwh
deliverable_terminal_energy_kwh = usable_terminal_stored_energy_kwh * discharge_efficiency
value_per_stored_kwh = discharge_efficiency * valuation_import_price
terminal_energy_value = deliverable_terminal_energy_kwh * valuation_import_price
```

`terminal_soc` 必须处于 exact battery model 的 `[min_soc_fraction, max_soc_fraction]` 规划范围；
valuation price 必须是有限非负数，零价格有效且产生零价值。结果保留 exact source input，从而保留
exact battery model identity。

## 解释边界

`terminal_energy_value` 是对 horizon 终点可用储能的 caller-assumed avoided future import-cost
value；它不是已实现收入、已实现成本节省、上网收入、套利利润或最终策略评分。TASK-162 不与
realized import cost 聚合，不引入 terminal SOC optimization、forecast-selected price、衰减、出口电价、
不确定性、MPC、Feasibility、Actuation、Simulator 或 Runtime。

后续任务如需定义 net economic score，必须显式定义 realized cost 与 terminal state value 的符号和
防止 double counting 的规则。
