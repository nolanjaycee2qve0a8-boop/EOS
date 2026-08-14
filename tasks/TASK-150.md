# TASK-150 Multi-Opportunity Schedule-Aware Physical Optimization Composition

## 目标

新增与 TASK-136、TASK-142 并行的单次 composition path：将 TASK-147 的
`MultiOpportunityHeadroomSchedule`、TASK-149 的 schedule-aware candidate planning，与既有
TASK-135 `ExplicitCandidatePhysicalRevision` 串联。该任务只证明 planning candidate 能够进入
既有物理修正层；不复制也不更改 SOC、功率或电池物理规则。

## 公共合同

- `MultiOpportunityPhysicalOptimizationInput`
- `MultiOpportunityPhysicalOptimizationSolveOutput`
- `MultiOpportunityPhysicalOptimizationBoundary`
- `DeterministicMultiOpportunityPhysicalOptimizer`

输入保存 exact `OptimizationProblem`、net-load configuration、battery state/model、
`PVOpportunityWindowConfiguration` 与 caller-owned duration。它没有 EMSDecision、Feasibility、
Actuation、Simulator 或 runtime state。

## 一次性 composition

```text
TASK-147 schedule calculation (once)
  -> TASK-149 candidate planning (once)
  -> TASK-135 explicit physical revision (once)
```

schedule 使用 exact `problem.forecast_horizon`、battery model、window configuration 和 duration。
candidate planner 接收 exact computed schedule 与原 problem/configuration/state/model。physical
revision 接收 exact `candidate_planning_result.final_output`，以及由相同 exact problem/state/model
构成的 TASK-135 physical input。

## Provenance 与职责边界

输出保留 source input、completed schedule、candidate planning result 与 physical output。调用方可从
schedule 导航到 opportunity sequence、selected ForecastPoint、每个 TASK-132 requirement、gap
depletion 和 schedule-adjusted target；也可从 candidate result 导航到原始 candidate、optional
TASK-148 reservation 与 final candidate；最终 physical output 保留 candidate constraint evidence、
revision evidence 和 final solution。

TASK-150 不直接分类 cheap-grid/PV charge，不读取 reservation target/power，不分段 opportunity，
不调用 TASK-132/TASK-147 的内部 calculator，也不执行 physical algorithm。planning 表达“希望什么”；
TASK-135 仍决定“物理上允许什么”。不会重跑 candidate、重算 schedule 或迭代收敛。

## 验证

测试以 tracking boundary 证明三个依赖各调用一次、full forecast 与 battery model identity 贯穿全链，
physical reviser 获得 exact planned final output。诊断 fixture 同时展示 schedule reservation 会调整当前
cheap-grid candidate，而后续 PV charge 仍可被 TASK-135 power/SOC evidence 继续下调；两层职责保持独立。
PV-surplus candidate 不经 reservation，也仍进入 physical revision。
