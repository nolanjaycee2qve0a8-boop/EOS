# Residential Device-Fact Command-Correlation Continuity Audit P0.12（候选规格）

> 状态：**已合并的 planning-only candidate documentation**。本文件通过 PR #213 合并到 main，merge SHA 为 `fbc2c6a84a11584a0c0887f074039cc5b815210e`，Quality checks 为 SUCCESS；它不是实现授权、不是公开 API，也不是对设备或协议的能力宣称。任何 P0.12 实现都必须取得后续、单独且明确的用户授权。

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

若获授权，最小公共合同可命名为：

- `DeviceFactCommandCorrelationContinuityInput`；
- `DeviceFactCommandCorrelationScopeDeclaration`；
- `DeviceFactCommandCorrelationContinuityFinding`；
- `DeviceFactCommandCorrelationContinuityAssessment`；
- `DeterministicDeviceFactCommandCorrelationContinuityAuditor`。

这只是命名和合同方向，不是已存在 API。候选 input 必须为一个 finite tuple，至少含两个**当前调用者提供的** P0.11 `DeviceFactCommandCorrelationInput`。它还必须携带新的 assessment identity、`assessment_as_of`、maximum age 及一个 explicit scope declaration。scope declaration 至少精确声明预期 transmission origin 与 P0.11 `DeviceFactSourceEpochRelationship`；它不能隐含生命周期事件。

未来 evaluator 只能同步处理该单一 input：对每个成员恰好调用一次冻结的 P0.11 evaluator，临时读取其 immutable PASS/GAP；不读取先前评估、不保留历史、不拥有时钟，也不跨调用累积事实。

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

本候选在独立只读 review 与用户明确 implementation authorization 前止步于文档。获授权后才可讨论生产代码、focused tests、mutation、完整门禁、独立复审及发布。
