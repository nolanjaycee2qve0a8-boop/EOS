# TASK-155 Economic Planning Objective / Cost Evidence Contract

## 目标

建立纯粹、确定性的电网进口电价跨时移能经济证据层。它回答“当前从电网充入
1 kWh，未来用电池交付该能量以避免进口电，毛经济价值是否为正”，而不改变任何
headroom、reservation、candidate、physical optimization、MPC 或 Simulator 行为。

## 公共合同

- `EconomicPlanningInput`：精确保留 caller-supplied `ForecastHorizon` 与
  `BatteryOptimizationModel`。证据按每 1 kWh 电网侧充电输入归一化，因此不需要
  duration、SOC、功率或充电量字段。
- `EconomicPlanningStepEvidence`：保留当前 `ForecastPoint`、按确定性规则选择的未来
  `ForecastPoint`、效率、break-even price、毛避免成本与毛 margin。
- `EconomicPlanningEvidence`：按 caller order 保存每个 forecast point 的证据，并验证
  exact point identity。
- `EconomicPlanningBoundary` / `DeterministicEconomicPlanningCalculator`：无状态纯计算边界。

## 经济语义

对 1.0 kWh 电网侧充电输入：

```text
stored energy = charge_efficiency
load-side delivered energy = charge_efficiency * discharge_efficiency
round_trip_efficiency = charge_efficiency * discharge_efficiency

gross avoided future import cost = future_import_price * round_trip_efficiency
gross shift margin = future_import_price * round_trip_efficiency - current_import_price
break-even future import price = current_import_price / round_trip_efficiency
```

`gross_shift_margin` 是未扣除 degradation、寿命、固定费用或其他经济成本的毛值；当前
域没有 export tariff，因此本 TASK 不推断 export economics。

## 未来价格与缺失价格

每个 source index `i` 只查找 `j > i` 的未来点，选取最高 import price；最高价格并列时
选择最早的 index。若 source point 缺失价格，该 source 的比较整体为 `UNAVAILABLE`。若
source 价格存在，则跳过缺失价格的 future point；若之后没有带价格的 future point，margin
为 `None`、分类为 `UNAVAILABLE`。任何情况下都不伪造 0 价格。

## 边界

TASK-147～154 负责未来 PV 的物理/headroom accounting；TASK-155 只提供经济价值证据。
Headroom 问“是否应为未来 PV 留出空间”，经济证据问“跨时移能是否有毛经济价值”；两者
都不直接决定电池动作。本 TASK 不读取 current SOC，不消费 schedule/reservation/candidate，
不产生 charge quantity 或 battery power，也不接入 Feasibility、Actuation、MPC、Simulator、
Runtime、Device 或 Command。

## 验证

覆盖效率方向、break-even、同价最早 future selection、末点/缺失价格、exact provenance、
immutability、边界无状态与 dependency isolation。明确样例：价格 `0.20 -> 0.90`、
充放电效率均为 `0.95` 时，margin 为 `0.90 * 0.95 * 0.95 - 0.20`，不在内部舍入。
