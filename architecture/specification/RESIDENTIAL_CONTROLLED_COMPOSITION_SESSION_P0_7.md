# Residential Controlled Composition Session — P0.7

## 1. Scope

P0.7 是一个同步、caller-owned、transport-neutral 的 session facade。它接受 caller 显式传入的前一 continuation，并为每个新 cycle 调用现有 P0.6 public composition boundary。它不是 daemon、loop owner 或 transport owner；没有 background work、thread、scheduler、clock service、persistence 或 auto-retry。

ADR-094 的 PROVISIONAL/CANDIDATE 记录保留为历史候选。本 specification 是本阶段的正式合同；它不授权 P0.8 或任何 network/hardware 扩展。

P0.7 已通过 PR #197 合并到 main，merge SHA 为
`f10852895b289c12d86f7d74fe84d33425411c15`。该发布状态不扩展本 specification 的 transport-neutral 边界，
也不表示 real transport、PCS/BMS、HIL、hardware control、field deployment 或硬件安全认证。

## 2. Minimal public API contract

实现必须只导出下列冻结 Python 名称与调用形状；不得在 implementation 前重命名、增加 transport abstraction 或改变 P0.6 composition 参数语义：

| frozen API | caller supplies / receives | ownership and lifetime |
| --- | --- | --- |
| `ControlledCompositionSessionCreationInput` | caller-owned `session_id`, fresh `ControlledEdgeRuntime`, `ResidentialDeviceAdapterBoundary`, `EdgeCommandHandoffBoundary`, `ControlledEdgeCompositionBoundary` | 只用于 `ControlledCompositionSession.create(input)`；创建不执行 cycle、采样 plant 或产生命令 |
| `ControlledCompositionSession` | `create(creation_input)` → session；只读 `initial_continuation` | caller-owned in-memory facade；creation 不执行 cycle；该属性返回首个 exact one-shot continuation，且仅同一 session 接受其 continuation |
| `ControlledCompositionSessionCycleInput` | new `FeasibleDecision`, fresh `EdgeCommandMetadata`, `timedelta duration`, `tolerance_kw` | caller authority 仅为 exact decision + fresh metadata；不得复用前一 cycle decision 或 metadata，且不接受 caller-supplied command |
| `session.run_cycle(cycle_input, continuation)` | exact current session continuation | 同步返回 `ControlledCompositionSessionCycleReceipt`；内部一次且仅一次调用 P0.6 `compose(ControlledEdgeCompositionInput)` |
| `ControlledCompositionSessionContinuation` | success receipt 中的下一 continuation | 当前 caller 交给下一 cycle；不可复制、序列化、hydration 或跨 session 使用 |
| `session.terminate(continuation)` | exact current continuation | 返回 `ControlledCompositionSessionTerminationReceipt`；以后所有 cycle fail closed |
| `ControlledCompositionSessionTerminatedError` / `ControlledCompositionSessionFailureError` | terminal use / failed cycle | 只携带不可执行审计 failure facts；不提供 restart 或 replay authority |

session creation 不接受 raw strategy/EMS request、historical decision/metadata、trace、ACK、actual power 或 evidence 作为 command authority。session 与 receipt 不提供 `from_dict`、factory、restore 或 replay API。

## 3. Per-cycle admission and identity

每个 `run_cycle` 都必须有新的 exact approved `FeasibleDecision` 与 fresh `EdgeCommandMetadata`。这些是 caller 的唯一 command authority；fresh 的最低含义是 decision/metadata 的 exact object identity，以及 metadata 的 command ID、sequence、issued_at、expires_at、requested power 与 mode 都不能来自 prior cycle 或被 session 改写。

`PowerCommand` 是 P0.6 实际传给 `ControlledEdgeRuntime.tick()` 的 current-caller public type，但它仅由 P0.6 内部的 P0.5 handoff 生成。P0.7 的 per-cycle gate 验证 returned evidence 的 `source_feasible_decision is cycle_input.feasible_decision`、`handoff_result.metadata is cycle_input.metadata`、`RuntimeLoopStep.caller_command is handoff_result.command`；若 admitted，`admitted_command` 也必须是该 exact internally generated command 并保留 `CURRENT_CALLER` origin。P0.7 不新增或替换 P0.6 参数，不能在 tick 前重建或验证 command。任何 equal-but-distinct source/metadata、重复 decision/metadata、跨 session continuation、跨 strategy evidence、未匹配 issued_at/sequence，或以 session ID/evidence 替代 caller decision/metadata 的尝试均 fail closed；不得以 history、trace、ACK、actual 或 safety-final power 恢复命令。

successful `CycleReceipt` 只允许：一次 P0.5 handoff、一次 P0.3 admission/runtime tick、一次 P0.4 observation、以及 admission 后恰好一次 P0.4 transmission。每次应保留 P0.5 source/metadata 与 internally generated `PowerCommand` lineage、P0.3 caller/admitted/safety-final facts、P0.4 request/ACK/actual evidence 的不可执行快照。冻结 P0.6 的 `transmission is None` 只表示 `admitted_command is None` 的 non-admission attempt；P0.7 必须终止并消耗该 attempt，不得返回 successful receipt 或将其解释为零 transmission 成功。

## 4. Session state, receipt and continuation

session bookkeeping 只能包含 session identity、strictly monotonic ordinal、已终态标记和不可执行 receipt linkage。它不得保存可重复执行的 P0.5 request、P0.3 prepared session、P0.4 adapter/handoff boundary、command factory、ACK/actual-derived power 或可写 lifecycle authority。

receipt 只保存不可执行审计事实。continuation 只保留下一次当前 caller 需要的 exact P0.3 next-runtime 与不可执行 session identity/ordinal；它不得从 receipt/evidence 反向取得 adapter、handoff、metadata 或 command authority。copy、deepcopy、pickle/reduce、hydration、serialization round-trip 与 cross-session use 必须拒绝。

## 5. Facts, termination and recovery

P0.3 reconciliation retained actual 是 logical execution fact；P0.4 actual telemetry 是独立 adapter observation。两者不能互相替代，ACK correlation 不能证明 physical completion。adapter evidence 永远不是 command authority。

termination、任何 `run_cycle` fault、malformed/unavailable adapter fact、P0.3 non-admission、ACK mismatch、identity/sequence/time mismatch 和 continuation misuse 都是 terminal fail-closed。失败尝试会消耗提交的 continuation，并永久终止该 session；不返回 `ControlledCompositionSessionCycleReceipt`、下一 continuation 或可重放 receipt。`ControlledCompositionSessionFailureError` 仅可附带不可执行 failure evidence。

recovery 不自动 retry、不生成命令、不恢复历史 power，也不能在旧 session 中继续。caller 必须显式创建新的 `ControlledCompositionSession`，并提供新 approved decision、fresh metadata，以及合法 fresh runtime、adapter 和 handoff boundary；再以新的 continuation 调用新的 session。

## 6. Frozen boundaries and non-goals

实现只能新增 session facade 生产文件和 focused test。P0.1–P0.6 production/tests/contracts、Residential EMS、Campaign A–F、PROVISIONAL 候选文件均为 zero-diff。向后兼容性要求既有 P0.6 单周期 public API 和其结果语义不变。

不实现 network、protocol、thread、scheduler、clock service、persistence、auto-retry、HIL、PCS/BMS、hardware、embedded mapping、real transport 或 field control。
