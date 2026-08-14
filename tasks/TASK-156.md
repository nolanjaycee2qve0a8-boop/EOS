# TASK-156 Economic + Headroom Grid-Charge Value Evidence

## 目标

把既有的 TASK-148 多机会 headroom reservation 证据，与 TASK-155 纯进口电价跨时移能
经济证据组合为当前 grid-charge opportunity 的只读结论。该合同回答：在 headroom 已允许
部分 grid charging 的前提下，这部分充电是否被未来避免进口电的毛经济价值支持。

## 公共合同

- `EconomicGridChargeValueInput`：保存 exact reservation result、exact economic evidence 与
  current source index。
- `EconomicGridChargeValueResult`：保留 requested、headroom-allowed 与
  economically-supported 三个互不混淆的功率，以及 exact selected economic step。
- `EconomicGridChargeValueBoundary` / `DeterministicEconomicGridChargeValueCalculator`：
  无状态、纯 evidence composition 边界。

## 一致性与身份

输入要求 reservation schedule 的 source `ForecastHorizon` 与 economic evidence 的 source
`ForecastHorizon` 为同一对象；两侧可追溯的 `BatteryOptimizationModel` 也必须是同一对象。
结果保持 exact reservation result、exact economic planning step、以及由后者可达的 current / best
future `ForecastPoint`。等值重建的 horizon 或 model 会被拒绝。

## 功率语义

```text
requested_grid_charge_power_kw
  = caller 原始请求（TASK-148 evidence）

headroom_allowed_grid_charge_power_kw
  = reservation_result.allowed_grid_charge_power_kw

economically_supported_grid_charge_power_kw
  = headroom_allowed，仅当 selected TASK-155 classification 为 POSITIVE
  = 0，否则（BREAK_EVEN / NEGATIVE / UNAVAILABLE）
```

`BREAK_EVEN` 采用保守的 0 kW：TASK-155 的 gross margin 尚未计入 degradation、不确定性、辅助
损耗与 opportunity cost。`UNAVAILABLE` 也为 0 kW，不猜测价格。`economic_support_applied` 表示
经济证据是否把已经允许的 headroom power 进一步降低；它不等同于 TASK-148 的
`reservation_applied`。

## 边界

TASK-148 问“headroom 允许多少 grid charge”；TASK-155 问“跨时移能是否有毛经济价值”；
TASK-156 问“已允许的那部分中有多少被经济证据支持”。即使 margin 为正，本任务也不会超过
headroom allowance，更不会在 requested/allowed 为零时生成充电功率。

本任务不重算 schedule、reservation 或 economic margin，也不修改 candidate、physical revision、
MPC、Feasibility、Actuation 或 Simulator。它不增加 discharge/export economics、degradation、
terminal SOC、求解器或 Runtime 行为。

## 验证样例

在 `current=0.20`、`future=0.90`、`eta_charge=eta_discharge=0.95`、headroom allowance
为 `1.2 kW` 时，TASK-155 margin 为 `0.61225` CNY per grid-input kWh，分类为 `POSITIVE`，
所以本合同支持 `1.2 kW`。在 `current=0.80`、`future=0.85` 的负 margin 样例中，同样的
headroom allowance 被经济证据收敛为 `0 kW`。
