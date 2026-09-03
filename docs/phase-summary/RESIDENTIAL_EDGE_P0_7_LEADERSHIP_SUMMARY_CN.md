# Residential Edge P0.7：受控组合会话已合并摘要

## 状态

P0.7 已通过 PR #197 合并到 main，merge SHA 为
`f10852895b289c12d86f7d74fe84d33425411c15`。该合并不是 production field deployment 或设备部署声明。

## 能力与产品价值

- 将 approved EMS `FeasibleDecision` 与 caller-owned metadata，以明确单 cycle 链路交给 P0.5、P0.3、P0.4。
- 每个 successful cycle 留下 decision → command → runtime → adapter evidence → receipt 的可审计链路。
- 以同步 one-shot continuation 让 caller 显式决定下一 cycle，而非由历史 evidence 自动重放功率。
- 将 P0.3 reconciliation 与 P0.4 actual telemetry 保留为两层事实，减少“ACK/遥测等于执行成功”的误读。

## 安全与 authority 边界

caller 只提供 exact approved `FeasibleDecision`、fresh `EdgeCommandMetadata`、duration 和 tolerance。
`PowerCommand` 在 P0.6 内由 P0.5 生成，不能由 caller、ACK、历史 trace、previous actual 或 receipt 重建。
每次尝试只运行一次 P0.6 composition；成功路径只对应一次 handoff、一次 runtime admission/tick 与一次
adapter transmission。任何 lineage、availability、correlation 或 continuation 异常均 fail closed，并终止
当前 session；recovery 必须创建新 session，不会 auto-retry 或 replay。

## 本地验证证据应如何理解

focused tests 关注 creation 无副作用、fresh caller inputs、exact command lineage、一次调用、跨 session
continuation 拒绝、copy/pickle 拒绝、terminal fault 与 fresh-session recovery。mutation 证据用于确认删除
关键 guard 会被断言捕获；它不代表生产路径已经发生故障，也不等于物理设备测试。

## 不能做什么

P0.7 不实现 network、device protocol、thread、scheduler、clock service、persistence、auto-retry、HIL、
PCS/BMS 通信、STM32/DSP 固件、hardware control、field deployment 或硬件安全认证。P0.4 evidence 也不能
单独证明设备已经完成真实物理执行。

## 下一阶段建议

后续产品化应优先投入真实 PCS/BMS 接口与安全边界、HIL、真实 telemetry 与 ACK 语义校准、故障/断电恢复及
运营审计。它们是从当前 transport-neutral 合同走向产品化的后续范围，不是已合并 P0.7 的已实现能力。
