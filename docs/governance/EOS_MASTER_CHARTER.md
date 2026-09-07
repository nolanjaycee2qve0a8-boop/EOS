# EOS Master Charter（建议治理文档）

> 状态：治理基础草案。它记录当前已接受的项目方向；任何具体行动仍以用户当前授权为最高优先级。

## 1. 最终目标

EOS 的长期目标是形成一条完整、可审计且权责分离的 energy control chain：

```text
现场/仿真 observation
→ Context / Forecast / Capability evidence
→ Objective / Strategy / MPC
→ DecisionIntent
→ Constraint / Feasibility
→ approved FeasibleDecision
→ Edge Command Handoff
→ Controlled Runtime / Safety / Lifecycle
→ Device Adapter
→ PCS/BMS or HIL boundary
→ ACK / actual telemetry
→ reconciliation
→ immutable audit evidence
```

这不是把所有能力塞进一个 Runtime。决策、仿真证据、边缘执行和发布证据分别拥有清晰边界；后层不能倒推取得前层的执行权限。这张图是长期目标，不代表 P0.6 已拥有 PCS/BMS、HIL、真实 transport 或现场能力。

## 2. 三条主线与 authority separation

| 主线 | 责任 | 不拥有的权力 |
| --- | --- | --- |
| Decision Intelligence | Forecast、策略、MPC、可行性与经济决策 | 设备执行事实、传输权力、历史命令重放 |
| Simulation / Evidence | 确定性仿真、验收、账务、Campaign 证据 | 生产 Runtime 或设备命令 authority |
| Edge Execution | caller-driven 命令准入、safety/lifecycle、适配器事实和审计 | 策略再计算、隐式调度、真实设备协议或现场控制 |

current-caller（当前调用方）提供的、已批准的输入是 command authority 的唯一来源。历史 trace、ACK、actual telemetry、序列化 evidence 或报告不得生成新命令、恢复 session，或重放历史功率。

## 3. 已冻结与已合并的事实

- Residential EMS 1.0 保持 functional freeze；Campaign A–F 的实现、数值和证据口径保持冻结。
- P0.1–P0.8 已合并。它们是产品化第一地平线的边界合同，不等于已经完成真实设备或现场产品。
- P0.6 是单周期、caller-driven、transport-neutral 的组合：P0.5 command handoff、P0.3 runtime admission/execution 与 P0.4 adapter audit evidence 在一个不可变、可审计的周期内组合。
- P0.6 不实现网络、真实 transport、协议、HIL、PCS/BMS/STM32/DSP 接口、硬件安全认证或现场控制。
- P0.7 已将 caller-owned、one-shot controlled-composition session 合并为软件合同；它不引入 scheduler、持久化、协议或现场控制。
- P0.8 已通过 PR #200 合并为 test-only adapter-conformance harness；它不把 transcript、ACK、actual 或 verdict 变成设备 authority 或物理执行证明。

## 4. 长期不变量

以下 15 项是跨阶段的最低治理约束：

1. Strategy request ≠ approved decision；策略请求不会自动成为可执行决定。
2. approved decision ≠ device execution；批准结果仍要经过 handoff、runtime、安全和设备边界。
3. 命令 authority 只来自 current-caller 的明确输入。
4. fail closed；不确定、损坏或不一致的边界事实不得被默认放行。
5. 无自动 replay；恢复、READY、ACK 或历史 evidence 均不生成命令。
6. 单 writer：一个 authority session / tick 只能执行一次。
7. planned、approved、safety-final 与 actual 是不同事实层，不能相互替代。
8. actual telemetry 是执行事实权威，但不追溯改写已完成的逻辑 reconciliation。
9. adapter evidence 不得自证设备执行成功；ACK/actual 必须保持其来源与语义。
10. evidence 与 continuation 分离；审计 evidence 不持有 live execution authority。
11. continuation 只服务当前 caller，不能被复制、序列化或 hydration 成新的 authority。
12. serialization 不得恢复 Runtime、Simulator、lifecycle、session 或 execution authority。
13. 每个边界保留 exact identity、sequence 与时间语义；不由下游重编号或改写。
14. validator 与 generator 不得以 common-mode 结果互相自证；关键 gate 需要独立断言、corruption 或 mutation 证据。
15. Simulation/Campaign 只产生证据，不反向改变冻结控制能力；frozen predecessor、真实 transport、硬件和现场主张都需各自的明确变更控制与证据。

## 5. 阶段治理序列

每个能力阶段遵循：

```text
capability-gap review → 用户阶段批准 → 受限实施 → focused validation
→ upstream/downstream/frozen regression → mutation / independent review
→ publication gate → 用户发布或合并决定
```

阶段完成不自动授权下一阶段。发现 authority、证据或冻结边界冲突时，先停止并提交最小可复现证据。

## 6. 后续能力地平线（候选，不是授权）

以下仅是待 capability-gap review 与用户阶段批准后才能讨论的候选：fake transport、protocol sandbox、HIL、embedded mapping，以及 field/productization。它们不表示已实现或已批准。
