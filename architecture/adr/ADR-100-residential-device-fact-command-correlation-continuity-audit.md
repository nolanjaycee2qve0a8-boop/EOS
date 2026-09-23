# ADR-100：Residential Device-Fact Command-Correlation Continuity Audit（P0.12 候选）

> 状态：**已实施、已验证并已合并的受限 audit 合同**。规划候选文档曾通过 PR #213 合并；P0.12 implementation 随 PR #215 合并到 main，main 为 `ce37c92a5daa33a588a2a33e721162f595212553`，implementation head `57d0f8828cdcb476509d8ef00933c9034143b106` 已包含在 main，Quality checks 为 SUCCESS。它仍仅是 deterministic、synchronous、caller-driven、test-only、audit-only 的 PASS/GAP 边界，不授权运行时状态、设备能力或发布。

## 背景与已合并边界

P0.10 已合并的 `DeviceFactLifecycleContinuity` 审计面向有限的通用设备事实快照及显式生命周期标签。它判断 `CONTINUITY`、断连、重启、重连、identity-epoch change 和时间不连续；它不是命令关联序列审计。

P0.11 已合并的 `DeviceFactCommandCorrelation` 审计面向**一个** caller-owned transmission / ACK / actual / source-epoch relationship 快照。它以 immutable PASS/GAP 证明该单个快照的关联一致性；其 evaluator 无跨调用状态、时钟、命令、device、runtime、adapter、session 或 replay authority。

因此仍存在一个严格受限的能力缺口：在同一 caller-declared correlation scope 中，无法审计有限多个、分别满足 P0.11 单快照合同的关联事实，是否保持唯一身份、严格顺序及声明的来源/epoch scope 一致。P0.10 的生命周期标签不能替代这项审计；P0.11 的单次结果也不能推断下一次调用的连续性。

## 决策：从规划候选落实为受限合同

P0.12 已落实为 **Residential Device-Fact Command-Correlation Continuity Audit**：一个 deterministic、synchronous、caller-driven、有限输入、immutable、test-only、audit-only 的 PASS/GAP 边界。以下规划候选的设计描述保留为该合同的历史与边界记录。

实现 input 只包含 caller-owned inert facts：

- 一个新的 continuity assessment identity、`as_of`、maximum age；
- 一个明确的 correlation-scope declaration（transmission origin 及 P0.11 source/epoch relationship 的预期值）；
- 至少两个有序的 P0.11 `DeviceFactCommandCorrelationInput` 事实输入。

实现必须对每个有效成员**恰好一次**复用冻结的 P0.11 evaluator，而不是重新实现其单快照规则，也不能把历史 `DeviceFactCommandCorrelationAssessment` 当作新事实。只有每个成员都是 P0.11 PASS，且整个序列满足唯一 assessment/transmission/actual identity、严格递增的 caller-declared transaction sequence 与 assessment time、顶层 freshness scope 以及准确的 declared scope，才可能得到 P0.12 PASS；任何缺失、重复、失序、跨 scope、P0.11 GAP 或类型不符都只能得到 explicit GAP。该 PASS 只表示审计事实在声明 scope 内一致，绝不表示命令执行、ACK 物理完成、actual 物理完成、P0.3 reconciliation、设备状态或设备生命周期。

P0.12 **不得**接受或产生 P0.10 lifecycle transition 标签，也不得把 source/epoch 差异解释为 disconnect、reboot、reconnect 或任何设备事件。跨 scope 的资料不是“自动连续”；它必须以 GAP 被诚实保留，或由调用方启动另一份独立的有限审计。

## Authority 与证据边界

输入和输出都必须是不可执行 evidence：

- 不持有或恢复 command、`FeasibleDecision`、metadata、device、runtime、adapter、prepared session、continuation、factory、transport 或 replay authority；
- 不调用 P0.3 runtime、P0.4 adapter、P0.5 handoff 或 P0.6–P0.8 composition；
- 不拥有 clock、thread、scheduler、registry、retry、持久化或跨调用状态；
- 不把 ACK 写成 physical completion，也不把 actual observation 写成 P0.3 reconciliation 的替代品；
- 不实现或暗示 protocol、network、CAN、Modbus、serial、HIL、PCS/BMS/DSP/STM32、硬件、现场控制、认证或部署。

未来 assessment 只能保留 assessment identity、`as_of`、PASS/GAP 与 immutable finding；它不得回存原始 input、成员 P0.11 assessment、live object 或可 hydration 的 authority。

## 验证与冻结

本 ADR 只授权受限实现与其验证，不授权发布。实现至少需要 focused contract tests、producer-corruption 与 gate-order mutation、P0.10/P0.11 frozen-path zero-diff、full regression、static/import/transport scan、independent review 与单独发布决定。

在任何未来授权前，P0.1–P0.11（含 P0.10 lifecycle continuity 与 P0.11 command-correlation）的生产合同、验证证据和已合并事实均保持冻结、零差异。

## 已合并状态

受限实现、focused/upstream/Residential/Campaign 回归、full pytest、Ruff、format、mypy、静态边界检查、pre-commit 与 isolated mutation evidence 已取得终态证据；PR #215 已合并，Quality checks 为 SUCCESS，main 为 `ce37c92a5daa33a588a2a33e721162f595212553`。该合并不扩大 P0.12 的 audit-only 边界；后续任何 runtime、device、adapter、protocol、network、HIL、hardware、field 或产品发布阶段均须新的 gap review 与明确用户授权。
