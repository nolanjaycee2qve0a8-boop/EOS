# Residential Edge P0.12 Candidate Validation Plan

> 状态：**受限实现 validation contract，未发布**。本记录的 planning-only candidate version 通过 PR #213 合并到 main，merge SHA 为 `fbc2c6a84a11584a0c0887f074039cc5b815210e`，Quality checks 为 SUCCESS。当前阶段允许 P0.12 implementation、test、mutation 与验证；尚无产品发布或外部设备能力证据。

## 1. 候选目标与可信边界

P0.12 候选是一个有限、同步、caller-driven、immutable、test-only 的 command-correlation continuity audit。它未来只能报告 PASS/GAP：在一个显式 correlation scope 中，多份 P0.11 caller-owned inert inputs 是否维持独特 identity、严格 sequence/time 顺序及同一声明 source/epoch relationship。

该候选不会执行或授权 command，不读取或传输设备，不保留 history/continuation，不创建 runtime/adapter/session，也不声称 ACK 是 physical completion 或 actual 是 P0.3 reconciliation。

## 2. 与 P0.10 / P0.11 的验证分界

- P0.10 的 lifecycle、disconnect、reboot、reconnect、identity epoch change 和 time discontinuity 测试不属于 P0.12；P0.12 不接收这些标签，也不产生设备生命周期结论。
- P0.11 的单一 transmission/ACK/actual correlation 正确性保持其冻结 evaluator 的职责。P0.12 的未来测试必须证明每个成员只经 P0.11 审计一次，而不能复制单快照 validator。
- P0.12 只新增跨成员、同 scope 的审计规则；它不把关联快照排序解释为设备物理行为或控制序列。

## 3. prospective focused matrix

当前受限实现的最低 focused coverage 应包括：

| 情形 | 期望证据 |
| --- | --- |
| 两个或更多有效、同 scope、严格递增的 P0.11 inputs | PASS；每个成员一次 P0.11 evaluation；无 authority 输出。 |
| 任一成员 P0.11 ACK unavailable、ACK mismatch、actual unavailable 或 relationship mismatch | GAP；P0.12 不把其他成员、ACK 或 actual 解释为修复或完成。 |
| 重复 assessment / transmission / actual identity | GAP；无 replay、无自动去重。 |
| sequence 或 assessment time 非严格递增 | GAP；不推断真实 transport ordering。 |
| origin 或完整 source/epoch relationship 逸出声明 scope | GAP；不标注 disconnect/reboot/reconnect。 |
| P0.11 assessment、P0.10 snapshot/transition 或未知对象冒充成员事实 | fail closed；不接受历史 assessment 为新事实。 |
| output copy/pickle/hydration 或历史 evidence 尝试恢复 authority | 无 execution authority 可恢复；output 不引用 raw inputs 或 live P0.1–P0.11 objects。 |
| import / invocation scan | 无 P0.3–P0.8 execution path、transport、network、thread、scheduler、persistence、protocol 或 hardware imports。 |

## 4. prospective mutation evidence

本阶段必须在临时 worktree 中证明以下退化能被独立测试杀死：绕过 P0.11-per-member delegation、接受历史 assessment、删除跨成员 uniqueness/ordering/scope gate、把 GAP 静默写为 PASS、或让 output 保存可执行 source authority。mutation 不得人工构造最终失败对象，也不得让 producer 与 validator 共用同一错误预期。

## 5. 计划中的门禁顺序

本阶段门禁顺序为：focused P0.12 → P0.10/P0.11 frozen regressions → Residential frozen/Campaign regressions → full pytest → Ruff/format/mypy/import and forbidden-dependency scans → `git diff --check` → mutation → independent review → 用户发布决定。

验证结论只能在终止证据取得后记录。P0.1–P0.11 已合并合同保持零差异；本实现不授权协议、网络、HIL、PCS/BMS/DSP/STM32、硬件、现场、认证或部署。
