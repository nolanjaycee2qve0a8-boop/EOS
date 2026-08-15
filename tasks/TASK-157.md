# TASK-157 Economic Schedule-Aware Candidate Planning

## 目标

新增并行的经济型 schedule-aware candidate-planning 边界。它将 TASK-149
所使用的 `NetLoadAwareBaselineOptimizer` 候选，与已完成的 TASK-147/148
headroom schedule/reservation 和 TASK-155/156 经济证据组合；只允许调整当前
时段（index 0）的 cheap-grid charge 候选。

## 公共契约

- `EconomicMultiOpportunityCandidatePlanningInput`
- `EconomicMultiOpportunityCandidatePlanningResult`
- `EconomicMultiOpportunityCandidatePlanningBoundary`
- `DeterministicEconomicMultiOpportunityCandidatePlanner`

输入保存 exact `OptimizationProblem`、配置、电池 state/model、headroom
schedule 与 `EconomicPlanningEvidence`。它强制 schedule 与经济证据都引用
同一个 `problem.forecast_horizon` 和同一个 `BatteryOptimizationModel`。

结果同时保留 exact source candidate、可选 reservation result、可选 economic
value result 和 final output。没有进入 cheap-grid 路径时，`final_output is
source_candidate_output`；发生调整时仅重建 index 0，所有 future steps 保留
exact object identity。

## 调用与分类规则

1. `NetLoadAwareBaselineOptimizer` 每次 `plan()` 恰好执行一次。
2. 当前候选为 `charge` 且 `PV > Load` 时，是 PV-surplus charging：不调用
   TASK-148 reservation，也不调用 TASK-156 economics。
3. 当前候选为 `charge` 且 `PV <= Load` 时，是 cheap-grid charging：TASK-148
   reservation 恰好一次，随后 TASK-156 value gating 恰好一次，均消费已经
   完成的 evidence。
4. `discharge`、`idle` 与 empty/unavailable candidate 保持原候选，不进入两条
   gating 边界。

最终 cheap-grid 充电功率始终满足：

```text
economic supported power <= headroom allowed power <= requested candidate power
```

`POSITIVE` 保留全部 headroom allowance；`NEGATIVE`、`BREAK_EVEN`、`UNAVAILABLE`
均收敛为 `idle / 0 kW`。经济层不产生比例缩放、不翻转为 discharge，也不改变
future steps。

## 边界

TASK-157 不重算 TASK-147 schedule 或 TASK-155 economic evidence，不执行
physical revision、MPC、Feasibility、Actuation 或 Simulator。PV-surplus
charging 明确不属于 grid-arbitrage economics，因此保持不受经济 gate 影响。
TASK-149 的既有 schedule-aware planner 未作任何语义修改。
