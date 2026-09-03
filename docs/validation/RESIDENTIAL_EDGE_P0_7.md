# Residential Edge P0.7 Validation — Controlled Composition Session

## 1. Contract status

本文是 P0.7 实施前的正式 validation contract，不是测试已通过的主张。实现完成前不得报告 focused、full pytest、mutation、CI 或 publication PASS。

ADR-094 的 PROVISIONAL validation candidate 保留为历史候选；本文取代其对 P0.7 的验证合同地位，而不删除该文件。

## 2. Focused acceptance matrix

| 类别 | 必须证明的事实 |
| --- | --- |
| Creation | session 创建及只读 `initial_continuation` 获取不执行 handoff/tick/observation/transmission，不采样 plant，不产生命令。 |
| New caller cycle | 每 cycle 要求新的 exact approved decision 与 fresh metadata；它们是 caller authority。history/trace/ACK/actual/evidence 不能成为输入或 command authority。 |
| Exact order | 每个 successful receipt 恰好一次 P0.5 handoff、一次 P0.3 admission/tick、一次 P0.4 observation，以及恰好一次 P0.4 transmission。冻结 P0.6 的零 transmission 仅表征 non-admission attempt；P0.7 必须将其 terminal fail-closed，消耗 continuation 且不返回 receipt。 |
| Authority and command lineage | `PowerCommand` 仅由 P0.6 内部 P0.5 handoff 生成并交给 P0.3 tick；P0.7 不接受 caller-supplied command。returned evidence 必须证明 P0.5 source/metadata 与 cycle input 同一对象，且 P0.3 `caller_command`、admitted 时的 `admitted_command` 与 P0.5 `handoff_result.command` 是同一 object。session ID 或 evidence 不能替代 caller decision/metadata；等值非同一或重复 decision/metadata fail closed。 |
| Isolation | caller/session/strategy 不能交换 continuation、receipt、metadata、evidence 或 ordinal。 |
| Frozen API | 仅导出 `ControlledCompositionSessionCreationInput`、`ControlledCompositionSession`、`ControlledCompositionSessionCycleInput`、`ControlledCompositionSessionContinuation`、cycle/termination receipts 和两种 terminal/failure errors；`run_cycle(cycle_input, continuation)` 内部一次调用 P0.6 `compose(ControlledEdgeCompositionInput)`。 |
| Continuation negatives | copy/deepcopy/pickle/reduce/hydration/serialization/cross-session continuation 均不能恢复 authority。 |
| Termination | `terminate(continuation)` 后旧 session/continuation 永久 fail closed；receipt 或历史 evidence 不能恢复 session。 |
| Fault/recovery | 任意 run_cycle fault、malformed/unavailable/ACK mismatch/non-admission（P0.6 的唯一零 transmission 表征）/identity-time mismatch/continuation misuse 终止 session 并消耗 continuation；无 cycle receipt、无 auto-retry、无历史 replay。recovery 只能显式创建新 session，提供新的 caller/decision/metadata 与 fresh runtime/adapter/handoff boundary。 |
| Fact separation | adapter actual/ACK 不能替代 P0.3 reconciliation，不能自证 physical completion。 |

## 3. Mutation and corruption matrix

mutation 只能在隔离临时 worktree 运行，且不得由人工拼装最终失败对象或 producer/validator common-mode 自证。至少需要：

1. 删除 fresh decision/metadata 或 P0.5→P0.3 lineage gate：以 corrupted producer 产生 equal-but-distinct source/metadata，或使 P0.3 caller/admitted command 不再是 P0.5 handoff command；定向测试必须显示 P0.6/P0.7 lineage assertion 失败。session ID 或 evidence 的替代不得让 mutation 存活；不得把 internally generated command 伪装为 caller input。
2. 删除跨 session continuation identity gate：定向测试必须显示 tick/adapter 调用非零，或原对象隔离断言失败。
3. 允许 receipt、ACK、actual、trace 或序列化对象生成命令：no-replay/caller-authority 测试必须失败。
4. 重复/跳过 handoff、tick、observation 或 transmission：实际 invocation-count 断言必须失败。
5. 让 termination/fault recovery 复用 prior metadata/power：新的 caller input 与 terminal no-replay 测试必须失败。
6. 让 adapter actual 覆盖 P0.3 reconciliation 或 ACK 断言 completion：事实分层测试必须失败。
7. 让 failed session 以同一 continuation 返回 receipt 或继续：terminal-consumption 测试必须失败；独立新 session 的 fresh-boundary recovery 对照必须通过。
8. 让 P0.6 non-admission 的 `transmission is None` 返回 successful receipt：non-admission terminal-consumption 测试必须失败；不得把零 transmission 伪装为成功。

每项需要记录最小 mutation、实际失败 node/assertion、无关错误排除、临时 worktree 清理及正式树零变化。

## 4. Regression and publication sequence

实现后，门禁顺序固定为：

```text
P0.7 focused
→ P0.1–P0.6 upstream/downstream focused
→ all edge runtime tests
→ Residential frozen regression
→ Campaign A–F regression
→ full pytest（终止 summary + exit code）
→ ruff / format / mypy / import / sensitive / generated-output / transport scans
→ P0.1–P0.6 frozen zero-diff
→ isolated mutation evidence
→ independent review
→ pre-commit
→ user-approved PR / CI / merge
```

P0.7 候选生产路径：`edge_runtime/controlled_composition_session/`；候选 focused test：`tests/unit/edge_runtime/test_controlled_composition_session.py`。在实现前这些路径不应被创建为伪证据。任何网络、协议、线程、scheduler、clock service、persistence、auto-retry、HIL、PCS/BMS、hardware、embedded mapping、real transport 或 field-control 变化均超出本 validation contract。
