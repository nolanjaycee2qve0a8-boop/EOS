# TASK-159 Economic Schedule-Aware MPC Cycle Integration

## 目标

新增一个并行的单周期 MPC orchestrator，将 TASK-158 的完整经济型
multi-opportunity physical final 转换为：

```text
Physical Final → OptimizationControlPlan → MPCCurrentAction → EMSDecision
```

## 公共契约

- `EconomicMultiOpportunityMPCCycleInput`
- `EconomicMultiOpportunityMPCCycleResult`
- `EconomicMultiOpportunityMPCCycleBoundary`
- `EconomicMultiOpportunitySingleMPCCycleOrchestrator`

`EconomicMultiOpportunityMPCCycleInput` 复用 exact
`PhysicallyAwareMPCCycleInput`，并补足 caller-owned candidate 与 opportunity
configuration；这是 TASK-158 所需而既有 input 未包含的两个 planning facts。

## 一次性链路

```text
MPC facts
→ OptimizationProblem
→ TASK-158 economic physical optimization
→ physical final solution
→ ControlPlan
→ CurrentAction
→ EMSDecision
```

TASK-158 optimizer、ControlPlan construction、CurrentAction extraction 与
EMSDecision translation 各恰好一次。ControlPlan 只能来源于 exact
`physical_output.final_output.solution`；不允许从 candidate、reservation 或
economic evidence 重建计划。

## Compatibility view

结果保留 `physical_cycle_view: PhysicallyAwareMPCCycleResult`。该 view 仅为既有
physical explanation 链提供兼容视图：复用 exact physical output、plan、action
和 decision，不会触发第二次 optimization、physical revision、计划构造、action
提取或 decision translation。

## 边界

TASK-159 不读取价格、economic classification、schedule target 或 reservation，
也不直接调用 TASK-147/155/157/135。经济/头部空间/物理语义全部由 TASK-158
拥有。它不接入 explanation、journal、CSV、daily runner、Feasibility、Actuation、
Simulator 或 Runtime。TASK-151 非经济 schedule-aware MPC 对照路径保持不变。
