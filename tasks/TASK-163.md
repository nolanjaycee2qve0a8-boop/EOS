# TASK-163 Economic Outcome / Net Cost Evidence

## 目标

TASK-161 比较的是已实现的 grid-import cost；TASK-162 为 horizon 终点可用电池能量建立 caller-price
valuation evidence。TASK-163 只把两份既有事实组合成有限的 accounting metric：

```text
net_economic_cost = realized_import_cost - terminal_energy_value
```

较低的 `net_economic_cost` 只在两条路径使用相同 terminal valuation semantics 时，才表示在本有限
accounting basis 下更优。它不是 profit；负值合法，只表示被 credit 的终端能量价值超过已实现购电支出。

## Public contracts

- `EconomicOutcomeInput`
- `EconomicOutcomeEvidence`
- `EconomicOutcomeBoundary`
- `DeterministicEconomicOutcomeCalculator`

输入是 caller 已计算的非负 `realized_import_cost` 与 exact TASK-162
`TerminalEnergyValueEvidence`。结果同时保留 exact source input 和 exact terminal evidence identity；
不重建或重新计算任何 TASK-162 value。

## 边界

本 TASK 不读取 Simulator result、grid trace、tariff、forecast、candidate、EMSDecision 或单独的 battery
state，不计算 import energy/cost，也不选择 terminal valuation price。它不接入 candidate planning、
optimization、MPC、runner、Feasibility、Actuation 或 control。

`net_economic_cost` 仅包含 realized grid-import energy cost 和 credited terminal stored-energy value；它不含
export revenue、battery degradation、auxiliary consumption、fixed tariff、demand charge、tax、forecast error、
uncertainty、terminal value 之外的 opportunity cost 或 capital cost。跨路径 valuation coherence 留给后续
comparison layer 显式验证。
