# ADR-094 — PROVISIONAL / CANDIDATE: Controlled Composition Session

> **NOT APPROVED FOR IMPLEMENTATION.** 本文是候选规划，不是 P0.7 冻结规格，不构成 Runtime、transport、hardware 或任何生产开发授权。

## Context

已合并的 P0.6 是一个明确、无状态、caller-driven 的 composition cycle：当前 caller 的 approved `FeasibleDecision` 和 metadata 经 P0.5 handoff，进入 P0.3 runtime，再产生 P0.4 transport-neutral audit facts。P0.6 故意不拥有多周期 session、scheduler、持久化或恢复 authority。

下一能力缺口不是“让历史 cycle 自动继续”。候选问题是：若未来需要连续多个显式 cycle，如何保持每个 cycle 的 current-caller、one-shot、no-replay 与 execution-fact 边界，而不让 trace、ACK、actual 或 serialization 变成命令 authority。

## Candidate decision boundary

若未来获得单独授权，候选 session 只能是 caller-owned 的受限 bookkeeping：

- 每个 cycle 必须由当时的 caller 新提供 approved `FeasibleDecision` 与 `EdgeCommandMetadata`；不得重放历史批准或自动生成 metadata。
- continuation 只能显式传递候选 session bookkeeping；不得从 ACK、actual telemetry、evidence、trace 或 serialized object 恢复 authority。
- 每个 cycle 保持一次 handoff、一次 admission、一次 runtime tick，且仅在 admission 后条件式一次 transmission。
- continuation、metadata 与 evidence 必须按 caller/session/strategy 隔离，不能跨 session 串用。
- current-caller、single writer、one-shot 与 no-replay 仍由现有边界强制；session 不得成为绕过 P0.3/P0.5/P0.6 gate 的入口。

## Facts and termination candidate

actual telemetry 仍是执行事实，不是 command authority；adapter evidence、ACK 或 available transmission 都不得自证 physical completion。候选 termination、fault 与 recovery 均 fail closed：结束的 session 不可恢复 authority；故障后的下一 cycle 只能依赖新的 caller input，而不能从历史 evidence 派生功率或命令。

## Explicit non-goals

本候选不引入 network、protocol、thread、scheduler、clock service、persistence、auto-retry、HIL、PCS/BMS、hardware authority 或 embedded mapping。它不修改 P0.1–P0.6 合同，也不将 adapter audit 叙述为真实设备执行证明。

## Required decision evidence before any implementation authorization

任何后续实现提案至少需要：独立 ADR/specification/validation contract；focused current-caller、session isolation、fault/recovery、no-replay 与事实分层测试；producer-corruption 与 authority-order mutation；continuation clone/serialization/replay negative tests；P0.1–P0.6 frozen zero-diff；独立 review、full regression、static/publication gate。

在这些 evidence 与用户阶段批准之前，本文仅记录候选边界。
