# PROVISIONAL / CANDIDATE — Residential Controlled Composition Session

> **NOT APPROVED FOR IMPLEMENTATION.** 这是规划合同草案，不是 P0.7 规格、公开 API 或实现授权；不得据此开发 Runtime、transport 或 hardware。

## 1. Candidate purpose

候选目标是描述多次、显式 caller-driven P0.6-style composition cycle 的安全连续性。它只讨论 authority bookkeeping；不是 loop owner，也不承诺真实设备连续运行。

## 2. Candidate input and cycle contract

每个 cycle 的候选输入必须包含当次 caller 的 approved `FeasibleDecision`、当次 caller-owned handoff metadata、显式 duration、当前受限 continuation 与既有 transport-neutral adapter boundary。

每次都应满足以下不变语义：

```text
new caller input
→ exactly one P0.5 handoff
→ exactly one P0.3 admission / runtime tick
→ exactly one P0.4 observation
→ zero or one P0.4 transmission (only after admission)
→ ACK / actual audit facts
→ immutable cycle evidence
```

历史 approved decision、metadata、request、safety-final power、ACK power、previous actual power、trace 或 evidence 都不得作为下一次命令输入。

## 3. Continuation and isolation candidate

候选 continuation 仅由当前 caller 显式持有，且只可表达安全的 session bookkeeping。它不得包含或恢复 adapter、handoff factory、request factory、historical command、prepared authority 或可 hydration 的 Runtime/Simulator/lifecycle/session/execution authority。

不同 caller、session 与 strategy 的 continuation、metadata、evidence、identity、sequence 和时间窗必须相互隔离。等值但非同一 identity、跨 session continuation、重复 metadata 或从审计 evidence 恢复的对象均应在任何 handoff、runtime tick 或 adapter 调用前 fail closed。

## 4. Facts and recovery candidate

P0.3 retained actual/reconciliation 与 P0.4 adapter actual telemetry 继续是独立事实层。actual telemetry 是执行事实，永不成为 command authority；ACK correlation 只证明请求关联，不能证明 physical completion。

termination、fault、unavailable facts、malformed facts、identity mismatch 和 recovery 都应 fail closed。recovery observation 不得提交或恢复历史命令；后续 cycle 只能由新的 caller input 尝试，且仍经过全部 P0.5/P0.3/P0.4 gate。

## 5. Non-goals and frozen boundaries

本候选不实现 network、protocol、thread、scheduler、clock service、persistence、auto-retry、HIL、PCS/BMS、hardware、embedded mapping、真实 transport 或 field control。它不得修改 P0.1–P0.6 的公开语义、Campaign、Residential EMS、已有 ADR/specification/validation，且不得把候选 session 叙述为已运行或已获批准。

## 6. Preconditions for a future specification

任何未来实现规格必须先获得用户阶段批准，并将 candidate 名称替换为已批准的范围；另需明确 lifecycle ownership、caller API、session termination、fault/recovery matrix、evidence serialization 负例、frozen paths 与验收命令。没有这些决定，本草案不可转化为代码任务。
