# TASK-152 Multi-Opportunity Schedule-Aware Explainable Daily Simulation Integration

## 目标

在不改变 TASK-128、TASK-138、TASK-144 runner 的前提下，新增一个有限的 24 小时 application runner。每个 caller-owned hour 调用一次 TASK-151 schedule-aware MPC cycle，并将真实 Simulator 状态反馈给下一小时。

## 新增契约

- `MultiOpportunityExplainableMPCDailySimulationInput`：复用 exact `ExplainableMPCDailySimulationInput`，仅补充 TASK-151 所需的 candidate 与 opportunity configuration。
- `MultiOpportunityExplainableMPCDailySimulationStepTrace`：保留 outer TASK-151 cycle、exact physical compatibility view、解释、journal、CSV、feasibility、handoff 与 simulator trace。
- `MultiOpportunityExplainableMPCDailySimulationResult`：保留完整的 24 小时 evidence 和唯一一次成功后的 CSV 写入结果。
- `MultiOpportunityExplainableMPCDailySimulationBoundary` 与 `MultiOpportunityExplainableMPCDailySimulationRunner`：无状态的有限执行边界。

## 每小时链路

`exact ForecastHorizon → TASK-151 outer cycle → physical_cycle_view → explanation / journal / CSV row → Feasibility → Handoff → Simulator`

`physical_cycle_view` 仅是兼容性引用，复用 outer cycle 已生成的 physical output、plan、action 与 decision；它不是第二次 MPC、优化、revision 或 decision。

## 实际反馈

- 第 0 小时 planning SOC 来自 caller 的 `initial_soc`。
- 后续每小时 planning SOC 仅来自上一条 Simulator trace 的实际 `next_state.soc`。
- 后续 EMS context grid power 仅来自上一条 Simulator trace 的实际 grid result。
- 不使用 projection、candidate、schedule target 或 forecast 的 SOC/Grid 值作为实际状态。

## CSV 兼容性限制

既有 decision CSV 继续记录 candidate、physical revision 和 final decision 的既有字段；不会在本任务中扩展为 schedule entry 数量、各机会 headroom、depletion、schedule target 或 reservation reason。完整 multi-opportunity evidence 始终可由 step trace 的 outer cycle 直接导航。

## 非目标

不新增 demo CLI、优化公式、schedule recurrence、reservation 公式、解释/CSV schema、pre-PV discharge、Zero Export、terminal SOC、solver、runtime scheduler 或 VPP。若任一小时失败，runner 立即停止，既不序列化也不写出 partial CSV。
