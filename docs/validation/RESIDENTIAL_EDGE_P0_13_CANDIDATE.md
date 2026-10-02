# Residential Edge P0.13 Candidate Validation Plan

> 状态：**planning-only / prospective candidate local draft**。本计划没有实现、pytest、mutation、CI、PR 或 release 结果。

## 1. 候选验证目标

P0.13 的未来验证只针对两个 caller-owned、有限 P0.12-shaped raw-input scopes 与一个显式 scope-handoff declaration 是否形成 audit-only PASS/GAP。每个 scope 都必须是有限的 P0.11 原始输入集合及其 P0.12 scope declaration；未来 P0.13 必须对每个 scope 恰好一次复用冻结 P0.12 auditor，不得复制、弱化或重新解释 P0.12 审计。它必须维持 deterministic、synchronous、test-only、immutable、caller-driven 边界。

## 2. future focused matrix

| 情形 | 期望未来证据 |
| --- | --- |
| 两个有限 scope 满足明确 identity/origin/source-epoch/member/global sequence/time handoff | PASS；只产生 immutable audit findings。 |
| 每个 scope 是当前 caller-owned 的有限 P0.11 raw-input 集合，且冻结 P0.12 auditor 分别恰好一次返回 PASS | PASS 的前置；P0.13 不重新实现或放宽 P0.12 scope 规则。 |
| 任一 scope 缺少 P0.11 raw inputs、P0.12 scope declaration，或 P0.12 审计非 PASS | GAP；不得以 P0.13 自行重判替代 P0.12。 |
| scope identity、origin、source/epoch relationship、成员 identity 或 declaration 缺失、unknown、冲突或失配 | GAP；不推断 lifecycle 或设备状态。 |
| 前 scope terminal member 或后 scope initial member 缺失、不是实际边界，或 declaration 与成员范围不一致 | GAP；不把排序解释为传输或物理行为。 |
| terminal → initial transaction sequence/time 重复、倒退、过期或未满足声明的方向性连续关系 | GAP；不把排序解释为传输或物理行为。 |
| 同一 input 内 duplicate scope identity，或同一 scope 实例出现两次 | GAP；单一 input 仅接受两个不同 scope 实例。 |
| historical P0.12 assessment、序列化 assessment 载荷或摘要伪装为 raw facts | GAP；无 replay、hydration 或 history authority。 |
| 跨调用的 scope reuse / reuse 检查诉求 | auditor 无 registry、跨调用 state 或 persistence，不能证明跨调用历史；PASS 不授予后续 delegation、replay、reuse 或 authority。 |
| source/epoch 变化 | 仅按 declaration 审计；绝不推断 disconnect、reboot 或 reconnect。 |
| ACK/actual/P0.3 reconciliation 被宣称为 handoff completion | GAP 或边界拒绝；ACK 不代表物理完成，actual 不替代 P0.3 reconciliation。 |
| command/runtime/adapter/device/session/continuation/trace/receipt/endpoint/credential/socket/transport 输入 | 公共边界拒绝；无 authority 获取。 |
| import/public surface | 无 predecessor execution-path、network、protocol、thread、scheduler、persistence、HIL 或 hardware imports。 |

## 3. future mutation evidence

未来 mutation 必须在独立临时 worktree 中，以真实 focused/static assertion 杀死以下退化：

1. 任一 scope 的冻结 P0.12-once gate 删除，或 P0.13 重写/放宽 P0.12 member-scope 规则；
2. scope identity、origin 或 member identity handoff gate 删除；
3. source/epoch declaration 或 exact relationship gate 删除；
4. terminal/initial member boundary、directional sequence/time continuity 或 freshness gate 删除；
5. same-input duplicate-scope、historical-P0.12-assessment/no-replay gate 删除；
6. source/epoch 变化被错误转换为 lifecycle inference；
7. ACK/actual/P0.3 reconciliation separation gate 删除；
8. 无跨调用 registry/state/persistence 与 PASS-no-future-authority boundary 删除；
9. authority-type/public-import boundary 删除。

不得以语法错误、fixture 错误、人工构造最终 PASS/GAP、或 producer/validator common-mode 自证作为 mutation kill。

## 4. future validation order

如未来获得实施授权，推荐顺序为：P0.13 focused → P0.10–P0.12 relevant frozen regressions → all Edge Runtime → Residential frozen → Campaign A–F → 一次有终止摘要和 exit code 的 full pytest → Ruff/format/mypy/public-import/frozen/sensitive/generated-output scans → pre-commit → isolated mutation evidence → independent authority review → learning/leadership docs sync → 用户发布决定。

P0.1–P0.12、Residential EMS 1.0 与 Campaign A–F 必须全程零差异。本候选不运行测试、不创建实现，也不授予协议、网络、设备、HIL、硬件或现场能力。
