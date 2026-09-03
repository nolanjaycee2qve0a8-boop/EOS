# ADR-095 — Residential Controlled Composition Session

## Decision

P0.7 定义一个同步、caller-owned、transport-neutral 的 multi-cycle session facade。它将多个明确的 P0.6-style cycle 按 caller 显式交接的 continuation 串联，但不拥有 background loop、worker、thread、scheduler、clock service、持久化或自动重试。

已合并的 ADR-094 和同名 PROVISIONAL/CANDIDATE 文档保留为历史候选记录；本 ADR、P0.7 specification 与 validation contract 正式取代其“候选合同”地位，但不删除或重写历史记录。

## Ownership and lifetime

候选公开对象在实现前必须遵循以下 ownership/lifetime 合同：

| 对象 | owner | lifetime | authority 约束 |
| --- | --- | --- | --- |
| `ControlledCompositionSession` | 当前 caller | 显式创建至显式 termination | 只协调 cycle；不生成命令或持久保存可执行 authority |
| `ControlledCompositionSessionCycleInput` | 当前 caller | 单一 cycle | 必须包含新的 approved `FeasibleDecision` 与 fresh `EdgeCommandMetadata`；caller 不提供 `PowerCommand` |
| `ControlledCompositionSessionCycleReceipt` | session/caller | 不可变审计记录 | 只含不可执行事实、ordinal 与 identity；不可恢复命令 |
| `ControlledCompositionSessionContinuation` | 当前 caller | 仅交给下一显式 cycle | 不可复制、不可序列化、不可 hydration；不得含 adapter/handoff factory 或历史 request |
| terminated receipt | caller/audit | 永久审计 | 不能重新启动 session 或恢复 execution authority |

`ControlledCompositionSession`、continuation、receipt 以及其持有的 Runtime/Simulator/lifecycle/session/execution authority 都不得 copy、deepcopy、pickle、reduce、hydrate 或从序列化恢复。审计 evidence、ACK、actual telemetry、trace、history、previous power 和 safety-final request 不是 command authority。

## Frozen public API shape

P0.7 实现必须只导出以下名称；不得以新增 transport abstraction 改变 P0.6 的调用边界：

- `ControlledCompositionSessionCreationInput`：包含 caller-owned `session_id`、合法 fresh `ControlledEdgeRuntime`、`ResidentialDeviceAdapterBoundary`、`EdgeCommandHandoffBoundary` 与 `ControlledEdgeCompositionBoundary`。
- `ControlledCompositionSession`：由 `ControlledCompositionSession.create(creation_input)` 创建；创建本身不执行 P0.6 cycle；只读 `initial_continuation` 返回首个 exact one-shot continuation。
- `ControlledCompositionSessionCycleInput`：包含新的 `FeasibleDecision`、fresh `EdgeCommandMetadata`、`timedelta duration` 与 `tolerance_kw`；不接受 caller-supplied `PowerCommand`。
- `ControlledCompositionSessionContinuation`：由成功 cycle 返回、仅交给同一 session 的下一显式 `run_cycle`；不可复制、不可序列化或跨 session 使用。
- `ControlledCompositionSessionCycleReceipt`：成功 cycle 的不可执行 P0.5/P0.3/P0.4 audit facts、ordinal 与下一 continuation。
- `ControlledCompositionSessionTerminationReceipt`：`session.terminate(continuation)` 的不可执行终态审计事实。
- `ControlledCompositionSessionTerminatedError` 与 `ControlledCompositionSessionFailureError`：分别表示已终态使用与本 cycle fail-closed 失败。

唯一 cycle 调用形状冻结为 `session.run_cycle(cycle_input, continuation) -> ControlledCompositionSessionCycleReceipt`。实现必须以 session 的 current runtime、adapter 与 handoff boundary 组装等价的 `ControlledEdgeCompositionInput`，并只调用一次既有 `ControlledEdgeCompositionBoundary.compose(input)`；不得改变 P0.6 参数语义或增加 transport 参数。

`PowerCommand` 是 P0.6 实际交给 P0.3 `ControlledEdgeRuntime.tick()` 的 current-caller 公共类型，但它只由 P0.6 内部的 P0.5 handoff 从 caller 的 exact `FeasibleDecision` 与 fresh `EdgeCommandMetadata` 生成。P0.7 不接受、重建或在 tick 前验证 `PowerCommand`；完成后的 P0.6 immutable evidence 必须证明 `RuntimeLoopStep.caller_command is EdgeCommandHandoffResult.command`，且 admission 时 `admitted_command` 仍是同一对象。`session_id`、strategy/evidence、ACK、actual 或 prior trace 都不能成为新 command authority，也不能替代 caller 的 decision/metadata 输入。

## Cycle authority contract

每一个 cycle 都必须由当次 caller 提供的 exact approved `FeasibleDecision`、fresh metadata 与显式 duration 发起。P0.6 内部唯一执行 P0.5 handoff 并把生成的 exact command 送给 P0.3；P0.3 的执行前 current-caller guard 继续在 P0.6 内部强制。P0.7 只从 returned immutable evidence 对照 P0.5 source/metadata lineage 与 P0.5→P0.3 command identity，不在 tick 前重建或验证命令。每个 cycle 的固定顺序为：

```text
one P0.5 handoff
→ one P0.3 admission / runtime tick
→ one P0.4 observation
→ exactly one P0.4 transmission for an admitted successful cycle
→ ACK / actual audit facts
→ immutable receipt + explicit continuation
```

冻结 P0.6 的零 transmission 表征仅为 `admitted_command is None`、`transmission is None` 的 non-admission attempt。P0.7 将该 attempt terminal fail-closed、消耗 continuation，且不返回 `CycleReceipt`；它不是成功 cycle 的零 transmission 分支。故 successful receipt 从不以 zero transmission 代表完成。

session 只保存不可执行 ordinal/identity bookkeeping；不得将 prior decision、metadata、command、ACK、actual、trace 或 evidence 变成下一 cycle 输入。caller、session 与 strategy 之间必须隔离 continuation、metadata、evidence、sequence、issued_at 和 time-window。single writer、one-shot、current-caller command identity 与 no-replay 继续由 P0.3/P0.5/P0.6 边界强制。

## Termination, fault and recovery

termination 是终态：后续调用必须 fail closed，不能通过旧 continuation、receipt 或历史 evidence 恢复 session。任何 `run_cycle` fault、malformed/unavailable fact、P0.3 non-admission、ACK mismatch、identity/time mismatch 或 continuation misuse 都是 terminal fail-closed：当前 session 与提交的 continuation 立即且永久不可再用；不返回 `CycleReceipt` 或任何可重放 continuation，只允许 `ControlledCompositionSessionFailureError` 携带不可执行 failure evidence。

recovery 不表示同一 session 的状态转换，也绝不提交或重放历史功率。恢复只能由 caller 明确创建全新 session，并提供新的 approved decision、fresh metadata，以及合法 fresh runtime/adapter/handoff boundary。新 session 的 cycle 仍重新经过 P0.5 handoff、P0.3 admission/tick 和 P0.4 audit。P0.3 reconciliation 与 P0.4 actual telemetry 保持独立事实层；adapter evidence 或 ACK 不证明 physical completion，也不追溯改写已完成的 P0.3 reconciliation。

## Compatibility, frozen paths and exclusions

P0.7 只新增 session facade 范围。P0.1–P0.6、Residential EMS、Campaign A–F、既有 adapter/handoff/runtime 公共语义必须 frozen zero-diff。候选生产路径是新的 `edge_runtime/controlled_composition_session/`；候选 focused tests 是 `tests/unit/edge_runtime/test_controlled_composition_session.py`。这些路径在本 ADR 阶段未创建代码。

P0.7 不实现 network、protocol、thread、scheduler、clock service、persistence、auto-retry、HIL、PCS/BMS、hardware、embedded mapping、real transport 或 field control。
