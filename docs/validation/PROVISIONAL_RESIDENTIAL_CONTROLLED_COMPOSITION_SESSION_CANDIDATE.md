# PROVISIONAL / CANDIDATE Validation Contract — Controlled Composition Session

> **NOT APPROVED FOR IMPLEMENTATION.** 本文不是 P0.7 测试结果、验收结论或实现授权。它仅规定未来候选若获批准时必须提供的证据。

## 1. Candidate evidence objective

未来候选必须证明多周期 session 没有把 P0.6 的单周期边界弱化：每个 cycle 均由新的 current-caller 输入驱动，且 P0.5 handoff、P0.3 admission/tick 与 P0.4 adapter audit 仍保持可计数、可审计的单次语义。

## 2. Focused test matrix

| 类别 | 候选负载与断言 |
| --- | --- |
| New caller per cycle | 每个 cycle 提供新的 approved decision 和 metadata；历史 approved input 不能自动重放。 |
| Invocation counts | 每 cycle 恰好一次 handoff、一次 admission/tick、一次 observation；只在 admission 后零或一次 transmission。 |
| Isolation | caller/session/strategy 不能交换 continuation、metadata、evidence 或 identity。 |
| One-shot/no-replay | reused metadata、trace、ACK、safety-final power、previous actual power 都不能重新提交命令。 |
| Continuation negatives | copy、deepcopy、pickle、reduce、hydration、clone 与跨 session reuse 必须拒绝。 |
| Fault/recovery | termination、fault、unavailable/malformed facts 与 recovery fail closed；恢复只能用新的 caller input。 |
| Fact separation | adapter actual/ACK 不替代 P0.3 reconciliation，也不自证 physical completion。 |
| Frozen scope | P0.1–P0.6 public behavior 和 Residential EMS/Campaign 路径零差异。 |

## 3. Candidate producer-corruption and mutation evidence

未来测试不得靠人工拼装最终失败结果或 producer/validator common-mode 自证。至少应以真实 public composition 路径杀死：

1. 删除 current-cycle identity/metadata gate；预期在 runtime/adaptor 前的 containment 断言失败。
2. 将 continuation 替换为 equal-but-distinct、跨 caller 或跨 session 对象；预期 fail closed 且无 handoff/tick/adapter 调用。
3. 允许 ACK、actual、trace 或 serialized evidence 生成新命令；预期 no-replay/caller-authority 测试失败。
4. 重复或跳过 handoff、tick 或 transmission；预期 invocation-count 与事实链测试失败。
5. 将 unavailable/malformed adapter facts 伪装为 completion，或让 adapter actual 覆盖 P0.3 reconciliation；预期事实分层测试失败。

每项 mutation 必须记录最小临时变更、实际失败测试、关键断言与清理证据；无关 import/fixture 错误不算杀死。

## 4. Future gates (not run by this draft)

若未来获实施授权，最小 gate 顺序为：candidate-focused → P0.1–P0.6 upstream/downstream and frozen regression → Residential/Campaign regression → full pytest with terminal summary and exit code → static/import/sensitive/generated-output scans → pre-commit → isolated mutation evidence → independent review → 用户发布决定。

本草案不运行 pytest、full gate、pre-commit、mutation 或 independent review；也不表明 network、protocol、thread、scheduler、clock service、persistence、auto-retry、HIL、PCS/BMS、hardware 或 embedded mapping 已存在。
