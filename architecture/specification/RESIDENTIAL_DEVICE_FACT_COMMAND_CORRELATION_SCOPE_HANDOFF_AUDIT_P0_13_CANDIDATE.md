# Residential Device-Fact Command-Correlation Scope Handoff Audit P0.13（候选规格）

> 状态：**planning-only / prospective candidate local draft**。没有 P0.13 implementation、test、mutation、CI、PR、merge 或 release 结论。

## 1. 目标

P0.13 候选为两个有限、caller-owned **P0.12-shaped raw-input scopes** 提供一次 deterministic、synchronous、immutable 的声明性交接审计。每个 scope 都是有限的 P0.11 `DeviceFactCommandCorrelationInput` 原始输入集合及其 P0.12 scope declaration，不是历史 P0.12 assessment。输出只能是 audit-only PASS/GAP assessment；它不创建、接受、发送或恢复任何 command 或 device authority。

## 2. 未来最小事实合同

未来公共合同可包含以下 immutable、inert 类型：

- `DeviceFactCommandCorrelationScopeHandoffInput`；
- `DeviceFactCommandCorrelationScopeFacts`；
- `DeviceFactCommandCorrelationScopeHandoffDeclaration`；
- `DeviceFactCommandCorrelationScopeHandoffFinding`；
- `DeviceFactCommandCorrelationScopeHandoffAssessment`；
- `DeviceFactCommandCorrelationScopeHandoffStatus`（`PASS` / `GAP`）；
- `DeterministicDeviceFactCommandCorrelationScopeHandoffAuditor`。

输入必须只含恰好两个有限、不同 scope identity 的 P0.12-shaped raw-input scope 实例、一个显式 declaration，以及新的 assessment identity、assessment `as_of` 和 freshness facts。每个 scope 实例只能在该单一 input 内出现一次。每个 scope 必须携带一份当前 caller-owned 的有限 P0.11 `DeviceFactCommandCorrelationInput` 集合、其 P0.12 scope declaration、scope identity、origin、完整 source/epoch relationship，以及从成员集合确定的 member identity、transaction sequence 与 assessment-time 范围。

未来 auditor 必须对每个有效 scope **恰好一次**调用冻结的 P0.12 auditor；P0.13 只读取该次审计的 immutable PASS/GAP 与该 scope 的原始边界事实来判断 scope-handoff，不得复制、弱化或重新解释 P0.12 的成员、scope、identity、sequence、time 或 freshness 规则。P0.12 historical assessment、其序列化载荷、摘要或任何伪装为 raw facts 的历史结果均为错误类型，必须 GAP；它们不是 runtime trace、receipt 或 execution authority。

declaration 必须明确两个 scope 的 handoff relation：允许的 scope identity/origin 关系、source/epoch relationship，以及**前一 scope 的 terminal member**和**后一 scope 的 initial member**各自的 identity、transaction sequence、assessment time 与允许的方向性连续关系。terminal/initial 边界必须与各自 raw-input scope 的实际最后/最先成员精确相符；后一 scope 的边界不得早于、重复于或与前一 scope 的边界范围冲突。关系不得由默认值、来源变化、排序或 evaluator 历史推断。

## 3. PASS/GAP 规则

未来 PASS 至少要求：

1. input 具有正确、有限、恰好两个 caller-owned P0.12-shaped raw-input scopes 和一个新的 assessment identity；
2. 每个 scope 都是当前 caller-owned 的有限 P0.11 raw-input 集合，且冻结的 P0.12 auditor 对每个 scope 恰好一次返回 PASS；P0.13 不重做或放宽 P0.12 规则；
3. declaration 明确且与两个 scope 的 identity、origin、source/epoch relationship 相匹配；
4. 每个 scope 的成员 identity 在其自身边界内有效，跨 scope 的 identity 关系符合 declaration；
5. declaration 指定的前 scope terminal member 与后 scope initial member 均是各自实际边界；其 transaction sequence 与 assessment time 在声明的方向上严格连续、无重复、无倒退、无范围冲突，并在新的 freshness scope 内；
6. 两个 scope identity 在该单一 input 内不同，且每个 scope 实例只出现一次；不会以 P0.12 historical assessment 代替 raw facts；
7. auditor 无跨调用 registry、state 或 persistence，不能证明跨调用 reuse；input 与输出不携带 execution、rehydration、history-reuse 或 replay authority。

任何缺失、unknown、冲突、重复、过期、失配、未声明关系、错误类型或历史 assessment 输入都必须 fail closed 为 GAP。特别是 terminal/initial member 缺失、范围不一致、sequence/time 倒序或重复，均不可由排序、默认值或历史调用补齐。P0.13 不重试、不自动补齐、不自动跨 scope 合并，也不产生替代事实。任何 PASS 也不授予后续 delegation、replay、reuse 或 authority。

## 4. P0.10 / P0.11 / P0.12 分界

- P0.10 仍是明确 lifecycle fact 的审计；P0.13 不从 source/epoch 变化推断 disconnect、reboot 或 reconnect。
- P0.11 仍负责单一 transmission/ACK/actual 的 correlation 边界；P0.13 不重新实现、也不把 ACK 或 actual 写作物理完成。
- P0.12 仍负责单一 correlation scope 内的连续性；P0.13 必须对每个 raw-input scope 恰好一次复用冻结 P0.12 auditor，并仅审计两个 scope 之间的显式 declaration handoff；它不接受 P0.12 历史 assessment 成为新事实。

P0.13 PASS 不表示 transmission、ACK、actual、P0.3 reconciliation、物理完成、设备可用、硬件 readiness、现场行为、认证或部署。

## 5. Authority 与非目标

候选不得接受、保存或输出 command、runtime、adapter、device、session、continuation、handoff authority、trace、receipt、endpoint、credential、socket、transport 或历史 assessment authority。output 仅可含 assessment identity、`as_of`、PASS/GAP 与 immutable findings，不能保留 raw facts 或 live predecessor objects。

明确排除 protocol、network、HTTP、CAN、Modbus、serial、thread、scheduler、persistence、retry、HIL、PCS/BMS、DSP/STM32、硬件/现场控制、认证和部署。

P0.1–P0.12、Residential EMS 1.0 与 Campaign A–F 完全冻结。本候选不构成 P0.13 实施或发布授权。
