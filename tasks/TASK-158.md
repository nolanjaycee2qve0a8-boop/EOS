# TASK-158 Economic Schedule-Aware Physical Optimization Composition

## 目标

新增一条并行 composition path，使 TASK-157 的经济型 schedule-aware candidate
进入既有 TASK-135 physical revision，而不复制或改变任一物理约束算法。

## 公共契约

- `EconomicMultiOpportunityPhysicalOptimizationInput`
- `EconomicMultiOpportunityPhysicalOptimizationSolveOutput`
- `EconomicMultiOpportunityPhysicalOptimizationBoundary`
- `DeterministicEconomicMultiOpportunityPhysicalOptimizer`

输入保留 exact problem、net-load configuration、电池 state/model、opportunity
configuration 与 caller-supplied control-step duration。输出完整保留 exact
headroom schedule、economic planning evidence、economic candidate planning result
及 physical output。

## 一次性组合链

```text
TASK-147 schedule
  -> TASK-155 economic evidence
  -> TASK-157 economic candidate planning
  -> TASK-135 explicit physical revision
```

每一注入边界恰好调用一次。schedule 和 economic evidence 均使用 exact
`problem.forecast_horizon` 与 exact `BatteryOptimizationModel`；TASK-157 接收
这两个已计算 artifact；TASK-135 接收 exact
`candidate_planning_result.final_output`。

## 责任边界

经济 candidate planning 回答：“当前 cheap-grid charge 中，多少同时受到
headroom 与 gross import-price economics 支持？”`NEGATIVE`、`BREAK_EVEN`、
`UNAVAILABLE` 可将当前 charge 收敛为 idle/0 kW。

Physical revision 回答：“这个已请求的 candidate 中，多少物理可行？”它可以继续
收紧正经济 candidate，但绝不能重新生成已被 economics 消除的 charge。PV-surplus
charge 仍绕过 TASK-157 内部的 grid-arbitrage gating，但之后仍进入 physical revision。

本任务不重算 TASK-147/155 的内部公式，不直接调用 TASK-148/156，不添加 MPC、
Feasibility、Actuation、Simulator、Runtime 或执行循环。TASK-150 非经济
schedule-aware 对照路径保持不变。
