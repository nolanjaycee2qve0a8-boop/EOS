# TASK-160 Economic Schedule-Aware Explainable Daily Simulation Integration

## 目标

将 TASK-159 的单次 Economic Schedule-Aware MPC cycle 组合为一个有限、caller-driven 的 24 小时仿真流程。每个小时只执行一次 outer MPC cycle，并将实际 Simulator SOC 与 Grid result 作为下一小时的输入事实。

## 新增公共契约

- `EconomicMultiOpportunityExplainableMPCDailySimulationStepTrace`
- `EconomicMultiOpportunityExplainableMPCDailySimulationResult`
- `EconomicMultiOpportunityExplainableMPCDailySimulationBoundary`
- `EconomicMultiOpportunityExplainableMPCDailySimulationRunner`

复用 TASK-152 的 `MultiOpportunityExplainableMPCDailySimulationInput`。它已经持有日仿真输入、24 个 caller-owned forecast horizons、MPC facts、battery planning model、locale、CSV path，以及 TASK-159 所需的 candidate/opportunity configurations；因此不引入近似重复的输入契约。

## 每小时链路

```text
actual EMS facts + exact caller horizon
  -> TASK-159 EconomicMultiOpportunity MPC cycle
  -> exact physical_cycle_view (compatibility only)
  -> explanation / journal / CSV row
  -> DecisionProvenance
  -> Feasibility
  -> Actuation handoff
  -> existing Simulator execution
  -> actual next SOC / actual Grid power
```

`physical_cycle_view` 是 outer cycle 的 exact compatibility artifact，不是第二个 cycle；不会再次执行 schedule、economic calculation、candidate planning、physical revision、control plan construction、current-action extraction 或 decision translation。

## 实际反馈语义

- Hour 0 的 planning SOC 来自 `daily_input.initial_soc`。
- 后续 hour 的 planning SOC 严格来自上一条 `simulation_trace.state.battery_result.next_state.soc`。
- 后续 `EMSContext` 的 grid power 严格来自上一条 `simulation_trace.state.grid_result.actual_grid_power_kw`。
- 每小时接收的 forecast horizon 是 exact `forecast_horizons[index]`；runner 不切片、克隆、重建或变异它。

## 可解释性与 CSV 限制

既有 explanation / journal / CSV contracts 继续消费 exact `physical_cycle_view`。当前 CSV 保持既有物理解释 schema，未扁平化 current price、selected future price、gross shift margin、economic classification、headroom allowance 或 economically supported power。完整经济证据始终可通过每小时 outer cycle 的 `economic_multi_opportunity_optimization_output` 导航。

## 边界

Runner 不读取或计算 price、margin、economic classification、schedule entries、reservation 或 cheap-grid charge；这些由 TASK-158/159 的上游边界拥有。TASK-160 不修改既有 generic、full-headroom、rolling-headroom 或 TASK-152 non-economic schedule-aware runner，也不新增 demo、runtime、scheduler、Feasibility/Actuation/Simulator 语义。

CSV 仅在 24 个小时全部成功后序列化并写入一次；任何更早失败都会 stop-first，且不会写出 partial CSV。

## 后续

下一步应在独立任务中对比 non-economic 与 economic schedule-aware 路径，至少覆盖可盈利与不可盈利的价格差场景；TASK-160 不新增最终行为比较 demo。
