# Residential Edge P0.10 设备事实生命周期连续性指南（已合并）

> **已通过 PR #207 合并到 main。** merge SHA 为
> `b78425f85fb3ccb7515cf6d69e0d0f2`，EOS CI `Quality checks` 为 SUCCESS。本文讲解
> P0.10 Device-Fact Lifecycle Continuity Profile；它不是设备接入说明、运行手册或现场安全证据。

## 1. 目标

P0.10 只回答一个审计问题：调用方显式提供的一段有限设备事实序列，是否按声明的生命周期转换规则保持连续且可解释。结果为不可变 `PASS` 或 `GAP` assessment，供审计和学习阅读。

## 2. 要解决的问题

P0.9 面向单个 `as_of` 时刻的 readiness 事实；它不判断相邻事实之间是否经历断连、重启、身份 epoch 变化、时间不连续或不恰当的恢复。P0.10 补足的是这段“事实是否连续”的审计空白，而不是生成新的控制意图。

## 3. 架构位置

```text
caller-owned immutable device facts + declared transition labels
                           |
                           v
      P0.10 deterministic, caller-driven, audit-only evaluator
                           |
                           v
              immutable PASS / GAP assessment evidence
```

它不调用 P0.1 safety、P0.2 device simulator、P0.3 runtime、P0.4 adapter 或 P0.5 handoff；也不反向改变 command、SOC、lifecycle、ACK、actual 或任何控制状态。

## 4. 输入

输入是调用方拥有的、按时间排序的不可变 device-fact snapshots，以及相邻快照对的闭集 transition labels。标签包含：

- `CONTINUITY`
- `DISCONNECT`
- `REBOOT`
- `IDENTITY_EPOCH_CHANGE`
- `TIME_DISCONTINUITY`
- `RECONNECT`

每个快照是已经提供的事实，而不是 P0.10 自行轮询、读取或补齐的设备数据。

## 5. 输出

输出 assessment 只保留不可执行的审计结论和 GAP findings。它不保留 live adapter、runtime、handoff、prepared request 或 input factory；也没有 restore、hydration、copy-to-authority 或 replay 入口。

## 6. 正常流

对相邻两个新鲜、身份和时间连续的事实，调用方声明 `CONTINUITY`。如果 identity、epoch、时间、source 和必要的 ACK/actual 事实都符合候选规则，assessment 可以给出 `PASS`。这个 `PASS` 只表示**所提供事实满足该审计规则**，不表示设备实际完成了物理动作。

## 7. 故障与恢复流

`DISCONNECT`、`REBOOT`、`IDENTITY_EPOCH_CHANGE` 和 `TIME_DISCONTINUITY` 都是显式 `GAP`，不能被静默抹平。`RECONNECT` 也不是自动恢复：它只有在紧邻的已声明不连续之后，且新的 caller-supplied facts 完整、身份/时间关系满足候选规则时，才可作为新的连续性起点。未知或缺失标签、identity reuse、历史 assessment 再输入、ACK/actual 缺失同样 fail-closed 为 `GAP`。

## 8. Authority 边界

P0.10 assessment 是 evidence，不是 command authority：

- 历史 assessment 不能作为下一次 evaluate 的新 authority；
- GAP finding 不能触发 retry、恢复、重放或安全动作；
- `actual_present` 只说明调用方提供了 actual telemetry fact；
- ACK 只用于 correlation audit；
- actual 和 ACK 都不能替代 P0.3 的 reconciliation，也不能证明 physical completion。

## 9. 安全边界

该层以显式 `GAP` fail-closed，而不是猜测缺失事实或默认 `0 kW`。这是一种审计分类，不是 PCS/BMS safety function，更不是针对不可信进程、协议消息或硬件攻击面的安全沙箱。

## 10. API 范围

公共形状可理解为：

```text
DeviceFactLifecycleContinuityInput
  -> DeterministicDeviceFactLifecycleContinuityEvaluator.evaluate(...)
  -> DeviceFactLifecycleContinuityAssessment
```

这是一份学习表示。P0.10 已通过 PR #207 合并；调用方仍不应把本节当作稳定 SDK、设备接入或硬件执行承诺。

## 11. 最小阅读示例

```text
facts:       S0  -- CONTINUITY --> S1  -- DISCONNECT --> S2
assessment:  PASS for S0/S1; explicit GAP for S1/S2
```

示例中的 `PASS` 不会撤销随后断连的 `GAP`，`GAP` 也不会调用 runtime 或 adapter。要重新建立审计连续性，调用方必须提供满足 `RECONNECT` 前提的新事实，而不能重用旧 assessment。

## 12. Tests 与 mutation 阅读

focused tests 应先覆盖正常 `CONTINUITY`，再覆盖六类标签和每类 GAP code。mutation 读取重点不是“测试数量”，而是测试是否能发现以下语义退化：identity reuse 被放行、未知标签被当作连续、断连 code 被消除、reconnect 前提被绕过、历史 evidence 被重用、ACK/actual 缺失被接受，或候选层引入 transport import。

## 13. 真实系统映射

未来 PCS/BMS/Edge telemetry 可能提供 source identity、identity epoch、设备观察时间、availability、request/ACK correlation 与 actual telemetry 等事实。真实系统仍需要设备接口、可信时间源、消息完整性、断线检测、恢复策略、现场故障处理和安全认证，才能可靠地产生这些 facts；P0.10 不连接 CAN、Modbus、HTTP、serial 或任何设备协议。

## 14. 已具备的审计能力

- 对调用方提供的有限 facts 做 deterministic continuity audit；
- 以 closed-set transition labels 让不连续原因可见；
- 将不完整、历史或矛盾事实明确归为 `GAP`；
- 保持 evidence 与执行 authority 分离。

## 15. 尚未具备的能力

P0.10 不提供网络、轮询、线程、scheduler、持久化恢复、真实 transport、HIL、PCS/BMS/STM32/DSP 集成、硬件控制、现场安全认证或产品部署。它也不恢复 runtime、lifecycle book、simulator 或 command authority。

## 16. 知识点与一页总结

阅读 P0.10 时，请始终分清三层：**事实是否被调用方提供**、**这些事实是否在审计规则下连续**、**设备是否真的完成物理执行**。P0.10 只覆盖前两层的审计；第三层仍属于真实设备 telemetry、P0.3 reconciliation 与未来经授权的产品化链路。

一句话：P0.10 是一个“把断连、重启、身份和时间断点明确写出来”的审计 profile；它宁可给出 `GAP`，也不会把历史 evidence 变成新的执行能力。
