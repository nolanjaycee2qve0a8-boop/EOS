# TASK-149 Multi-Opportunity Schedule-Aware Candidate Planning

## 目标

新增一个与 TASK-134 并行的 candidate-planning boundary。它消费既有的 TASK-147
`MultiOpportunityHeadroomSchedule` 与 TASK-148 reservation evidence，并且仅可能调整
当前（索引 0）cheap-grid charging candidate。TASK-134、rolling/full headroom、physical
revision、MPC 和 simulator 路径均保持不变。

## 公共合同

- `MultiOpportunityCandidatePlanningInput`
- `MultiOpportunityCandidatePlanningResult`
- `MultiOpportunityCandidatePlanningBoundary`
- `DeterministicMultiOpportunityCandidatePlanner`

输入保留 exact `OptimizationProblem`、net-load configuration、battery state/model 与已完成
schedule。`control_step_duration_seconds` 为 TASK-148 的显式 caller-owned 换算数据；不会从
clock、timestamp 或 future step 推导。

## 语义与 provenance

```text
NetLoadAwareBaselineOptimizer (once)
  -> source_candidate_output
  -> classify current candidate step
  -> optional TASK-148 reservation (at most once)
  -> final_output
```

当前 step 为 `charge` 且 `PV > Load` 时属于 PV-surplus charging：不调用 reservation，
`final_output is source_candidate_output`。当前 step 为 `charge` 且没有 PV surplus 时属于
cheap-grid charging：以 exact schedule/state/model、candidate requested power 和显式 duration
调用 TASK-148。discharge、idle 和空/unavailable candidate 均不调用 reservation。

若 allowance 未降低 request，final output 保持 source output exact identity。若减少，只有
index 0 被替换；所有 future `OptimizationSolutionStep` 仍是 source candidate 的 exact object。
零 allowance 收敛为 idle/0，不会反转为 discharge。partial allowance 保持 charge direction。

`MultiOpportunityCandidatePlanningResult` 同时保留 exact input、source candidate、optional
reservation result 与 final output，使调用方可以区分原始 candidate 与 schedule-aware
allowance。schedule/model/configuration 的 value-equal reconstruction 不替代 identity lineage。

## 边界

TASK-149 不重新分段 PV opportunities，不运行 TASK-132/TASK-147，不计算 depletion，不调用
physical revision，也不接入 MPC、feasibility、actuation 或 simulator。它不改变 net-load
candidate rule、价格阈值或 tariff 语义；只消费已完成 evidence 调整当前 cheap-grid request。

## 验证

测试覆盖 source candidate exactly-once、reservation at-most-once、PV surplus 不受限、
discharge/idle 不变、partial/zero allowance、future step exact identity，以及 TASK-146/147/148
风格的双 opportunity schedule：later opportunity 尚需 headroom 时，schedule-adjusted target
会令当前 allowance 比 first-opportunity standalone target 更严格。
