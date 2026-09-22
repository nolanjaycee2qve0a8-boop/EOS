# Residential Device-Fact Command-Correlation Continuity Audit P0.12（候选规格）

> 状态：**受限实现规格，未发布**。本文件的 planning-only candidate version 通过 PR #213 合并到 main，merge SHA 为 `fbc2c6a84a11584a0c0887f074039cc5b815210e`，Quality checks 为 SUCCESS。当前实现授权只建立 test-only audit API；它不是设备、协议或发布授权。

## 1. 目的

P0.12 候选拟为同一 caller-declared correlation scope 内的有限相关快照提供 deterministic、synchronous、immutable 的审计 PASS/GAP。它解决的仅是：多个 P0.11 级别 command-correlation facts 是否可被诚实地读为一个无重复、无失序、无未声明来源/epoch 跳变的**审计序列**。

它不创建、接收或恢复 command authority；不执行控制；不向设备传输；不读取设备；不持有 runtime continuation；也不把审计序列称为真实物理命令序列。

## 2. 与既有阶段的非重叠范围

| 阶段 | 已有职责 | P0.12 不重复之处 |
| --- | --- | --- |
| P0.10 | 通用事实快照的 lifecycle transition、disconnect/reboot/reconnect/epoch/time discontinuity | P0.12 不接受 lifecycle label，不判断设备生命周期，也不从 source/epoch 变化推断设备事件。 |
| P0.11 | 一个 transmission/ACK/actual/source-epoch relationship 快照的关联正确性 | P0.12 不重写该规则；每个成员须经冻结 P0.11 evaluator 一次。P0.12 只审计跨成员的 scope、identity、sequence 与 time continuity。 |

P0.12 不会将 P0.10 `CONTINUITY` 视为 correlation continuity 的证据，也不会将任一历史 P0.11 assessment 当作新的 caller fact。

## 3. prospective contract

最小公共合同为：

- `DeviceFactCommandCorrelationContinuityInput`；
- `DeviceFactCommandCorrelationScopeDeclaration`；
- `DeviceFactCommandCorrelationContinuityFinding`；
- `DeviceFactCommandCorrelationContinuityAssessment`；
- `DeterministicDeviceFactCommandCorrelationContinuityAuditor`。

input 必须为一个 finite tuple，至少含两个**当前调用者提供的** P0.11 `DeviceFactCommandCorrelationInput`。它还必须携带新的 assessment identity、`assessment_as_of`、maximum age 及一个 explicit scope declaration。scope declaration 精确声明 scope identity、预期 transmission origin 与 P0.11 `DeviceFactSourceEpochRelationship`；它不能隐含生命周期事件。

evaluator 只能同步处理该单一 input：对每个有效成员恰好调用一次冻结的 P0.11 evaluator，临时读取其 immutable PASS/GAP；不读取先前评估、不保留历史、不拥有时钟，也不跨调用累积事实。成员自身事实 freshness 继续由其 P0.11 input 负责；顶层 maximum age 仅约束 member assessment time 对顶层 `assessment_as_of` 的 freshness。

## 4. prospective PASS/GAP 语义

P0.12 PASS 的必要条件是：

1. input 是类型正确、有限且至少两个成员的 caller-owned inert fact 集合；
2. 每个成员经 P0.11 恰好一次审计为 PASS；
3. continuity assessment、每个 P0.11 assessment、每个 transmission identity 与每个 actual observation identity 均唯一；
4. 成员按 caller-declared transaction sequence 与 assessment time 严格递增，且每一项满足其自身 freshness scope；
5. 每个成员的 transmission origin 与完整 source/epoch relationship 精确匹配声明的 correlation scope。

任一条件缺失、重复、乱序、过期、范围不符、P0.11 GAP、历史 assessment 伪装成事实或未知类型，均为 explicit GAP。P0.12 不自动跨 scope 合并，不自动把 GAP 修复成 PASS，不重试，也不创建替代 command。

P0.12 PASS 不表示：ACK 已导致物理完成；actual 已替代 P0.3 retained actual/reconciliation；任何 command 被执行；任何 lifecycle transition 发生；或任何真实设备链路可用。

## 5. 证据与非目标

未来 output 只能包含新的 assessment identity、`as_of`、status 和 immutable findings。它不得保留 caller input、P0.11 input/assessment、command、metadata、runtime、device、adapter、session、continuation、factory 或 serialization/hydration/replay entry。

本候选明确排除 protocol/network/CAN/Modbus/serial、thread/scheduler、persistence/retry、HIL、PCS/BMS/DSP/STM32、硬件/现场控制、认证、部署，以及任何 production runtime authority。

## 6. 后续 gate

当前授权止于受限实现、focused tests、mutation 与完整门禁；仍须经独立只读 review 和用户单独发布决定。它不授权真实设备或外部能力。

## 7. 本地验证状态

本候选已完成本地 focused、upstream、Residential/Campaign、full pytest、static 与 pre-commit 门禁，且 mutation evidence 已在隔离 worktree 中取得。它尚未 push、PR 或 merge；这些本地结论不替代独立 review 或用户发布授权。
