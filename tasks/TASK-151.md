# TASK-151 Multi-Opportunity Schedule-Aware MPC Cycle Integration

## 背景

TASK-150 已将多机会 PV headroom schedule、候选计划与显式物理修正组合为一次完成的优化产物，但该产物尚未进入 MPC 的“当前一步”决策链。

## 目标

新增并行的单周期适配边界，将 TASK-150 的**物理修正最终解**转换为：

`OptimizationControlPlan → MPCCurrentAction → EMSDecision`

## 新增契约

- `MultiOpportunityMPCCycleInput`：保留既有 `PhysicallyAwareMPCCycleInput` 的精确身份，并注入 TASK-150 所需的 candidate 与 opportunity 配置。
- `MultiOpportunityMPCCycleResult`：保留 TASK-150 的完整外层输出、control plan、当前动作、决策和兼容性 physical-cycle view。
- `MultiOpportunityMPCCycleBoundary`：无状态、单周期抽象边界。
- `MultiOpportunitySingleMPCCycleOrchestrator`：仅调用一次 TASK-150 边界，再各调用一次 plan construction、current-action extraction 与 decision translation。

## 核心语义

1. control plan 的唯一来源是 `physical_output.final_output.solution`；candidate、reservation 和 schedule 不得直接驱动当前动作。
2. 兼容性 `physical_cycle_view` 仅复用已生成的 exact physical output、plan、action 与 decision，不触发第二次优化或物理修正。
3. caller 的 context、forecast、objectives、battery state/model、candidate configuration 与 opportunity configuration 均保持 exact identity。
4. 本任务不读取或解释 schedule entries，不重复 TASK-147、TASK-149、TASK-135 的逻辑。

## 非目标

不新增 solver、预测、feasibility、actuation、simulator、daily runner、解释/journal/CSV 或循环调度；不会修改 TASK-122、TASK-137、TASK-143 的冻结路径。
