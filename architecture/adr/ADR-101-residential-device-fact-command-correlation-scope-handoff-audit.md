# ADR-101：Residential Device-Fact Command-Correlation Scope Handoff Audit（P0.13 候选）

## 状态增补（2026-10-02）：P0.13 实现已合并

P0.13 实现经 [PR #218](https://github.com/nolanjaycee2qve0a8-boop/EOS/pull/218) squash merge 到 main：
`c7ee7ffdfb20b9133c5955c6921233cfccaf5fe5`；主线 [CI run 36997610237](https://github.com/nolanjaycee2qve0a8-boop/EOS/actions/runs/36997610237) 的 API 结论为 success。
作者终态验证、最终独立 KEEP、证据来源与限制见[实施证据的最终合并摘要](../../docs/validation/RESIDENTIAL_EDGE_P0_13_IMPLEMENTATION_EVIDENCE.md#最终合并与审核摘要2026-10-02)。
本增补仅更新状态与证据链接，不改变下面的规范规则。

以下保留 candidate 阶段原文；其中 planning-only、未来、尚未发生、另行授权等叙述属于当时快照，
不表示当前实现仍未开始，也不代表自动授权下一阶段。实现合并与本轮文档收尾是不同事项；
本轮文档候选尚待独立文档复核及主对话后续处理，不据此声明文档已发布。

## 候选历史原文（保留）

> 状态：**planning-only / prospective candidate local draft**。本 ADR 不是实施、测试、mutation、CI、PR 或发布记录；任何 P0.13 实施均须新的明确用户授权。

## 背景

P0.12 已合并，且只审计单一 caller-declared correlation scope 内有限 P0.11 `DeviceFactCommandCorrelationInput` 原始事实的 identity、sequence 与 time continuity。每个 P0.12 scope 都以当前调用者提供的有限 P0.11 输入组成，并由冻结的 P0.12 规则独立审计；它刻意不把一个 scope 的结尾变成另一个 scope 的起点，也不授予跨 scope 的推断权。

仍有一个受限缺口：调用方可能拥有两个有限、彼此独立的 **P0.12-shaped raw-input scopes**，并需要审计它们是否按一个**显式声明的 scope-handoff** 一致衔接。这里的 scope 必须仍是原始 P0.11 输入集合及其 P0.12 scope 声明，而不是 P0.12 的历史 assessment。P0.12 的 PASS 不能自动成为这种交接的证据；P0.10 的 lifecycle semantics 也不能从 source 或 epoch 差异中被隐式补入。

## 决策：仅规划一个声明性交接审计

P0.13 候选是 deterministic、synchronous、caller-driven、test-only、immutable、audit-only 的 PASS/GAP 评估边界。它未来只审计：

- 两个有限 caller-owned、P0.12-shaped **原始 P0.11 input** scope；
- 一个显式 scope-handoff declaration；
- 新的 assessment identity、`as_of` 与 freshness facts。

每个 scope 必须是一个当前调用者提供的有限 P0.11 `DeviceFactCommandCorrelationInput` 集合及其精确 P0.12 scope declaration。未来 P0.13 必须对每个 scope **恰好一次**复用冻结的 P0.12 规则；它不得复制、弱化、替换或重新解释 P0.12 的 scope 内审计。历史 P0.12 assessment 无论以对象、序列化载荷、摘要或伪装 raw facts 的形式出现，均不得作为新的 authority 或事实。

候选必须核验 scope identity、origin、source/epoch relationship、成员 identity，以及**前一 scope 的末端成员到后一 scope 的首端成员**在声明性交接中的方向性 sequence/time 边界。declaration 必须明确指向这两个边界成员及其允许的 sequence/time 关系；不得以全局默认值、排序、历史 evaluator 状态或 source/epoch 变化补推。它也不能把两个 scope 自动合并。

在单一 P0.13 input 内必须恰好提供两个不同的 scope 实例；scope identity 不可重复，且每个实例只能在该 input 中出现一次。任何 scope identity/origin/source-epoch relationship/成员 identity/sequence/time 的缺失、unknown、冲突、失配、重复、乱序、过期或未声明交接均只能返回 explicit GAP。尤其是：前 scope 末端或后 scope 首端缺失、方向倒置、成员或边界值重复、或 declaration 与实际 scope 范围不一致，均为 GAP。

## 非推断与 authority 边界

source 或 epoch 的变化绝不意味着 disconnect、reboot、reconnect 或任何设备生命周期事件；那些仅属于 P0.10 的显式 lifecycle 语义。P0.13 PASS 仅表示有限 caller facts 符合本候选的声明性交接规则，绝不表示：

- transmission、ACK、actual 或 P0.3 reconciliation 已发生或一致；
- 物理完成、设备可用、硬件 readiness、现场行为或产品发布；
- command、device、runtime、adapter、session、continuation、handoff、trace、receipt、endpoint、credential、socket、transport 或 replay authority。

未来 input/output 均应为 inert immutable evidence。auditor 不拥有跨调用 registry、state 或 persistence，因而不能证明任何跨调用 scope reuse；assessment 不能保存 live inputs、不能 hydration/restore/replay 成任何 execution 或 authority object。任何 PASS 不授予后续 delegation、replay、reuse 或 authority，也不能拥有 clock、thread、scheduler、registry、retry 或持久化。

## 明确排除

候选不实现 protocol、network、HTTP、CAN、Modbus、serial、thread、scheduler、persistence、retry、HIL、PCS/BMS、DSP/STM32、硬件或现场控制、认证或部署。

P0.1–P0.12、Residential EMS 1.0 与 Campaign A–F 保持冻结、零差异。P0.13 的任何实现、验证、独立审阅或发布都必须是另行授权的阶段。

## 后续门禁

如未来获实施授权，最低门禁应包括 focused contract tests、独立 semantic mutation、前置阶段冻结核验、Campaign 与 full regression、static/import boundary checks、pre-commit、独立 authority review、学习材料同步以及独立发布决定。上述事项在本候选中均尚未发生。
