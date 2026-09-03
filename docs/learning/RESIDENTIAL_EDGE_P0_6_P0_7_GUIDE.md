# Residential Edge P0.6–P0.7 学习指南

## 状态与用途

本指南把 P0.3、P0.4、P0.5 与 P0.6 串成可阅读的单周期链路，并说明 P0.7 如何以 one-shot continuation
串接多个显式 cycle。P0.7 已通过 PR #197 合并到 main，merge SHA 为
`f10852895b289c12d86f7d74fe84d33425411c15`；该事实不表示它已成为 production Runtime 或现场设备能力。

新指南是必要的：既有学习手册、架构说明、Demo 与 TASK 记录分别承担全局知识、架构、演示与历史台账职责，
不能在不重复改写历史内容的前提下容纳一份可复现的 P0.6→P0.7 组合周期教程。本文件集中该教程，其余四份
文档只提供导航与边界摘要。

## 1. 一页总览

**目标：**让当前 caller 只凭一份已批准的 `FeasibleDecision`、一份新的 `EdgeCommandMetadata`、duration
与 tolerance，发起一个同步、可审计、transport-neutral 的 Edge composition cycle。

```text
caller
  │ exact FeasibleDecision + fresh metadata + duration/tolerance
  ▼
P0.5 handoff                 P0.3 controlled runtime       P0.4 adapter audit
FeasibleDecision ──► PowerCommand ──► admission/tick ──► observation/transmit/ACK/actual
                                                                    │
                                                                    ▼
                                                        P0.6 immutable evidence
                                                                    │
                                                                    ▼
                                              P0.7 receipt + next one-shot continuation
```

每次尝试由一个当前 caller 发起；P0.6 compose 一次、P0.5 handoff 一次、P0.3 admission/tick 一次，P0.4
只在 admitted 的成功 cycle 中 transmission 一次。这是逻辑调用与证据链，不是网络调用、真实设备传输或物理完成声明。

## 2. 为什么已有 P0.3 / P0.4 / P0.5 仍不足以构成 cycle

| 阶段 | 解决的工程问题 | 它没有解决的事 |
| --- | --- | --- |
| P0.3 Controlled Runtime | current-caller admission、lifecycle/safety、one-shot logical execution 与 reconciliation | 不将 FeasibleDecision 转成 command，也不产生 adapter 事实 |
| P0.4 Device Adapter | request、observation、ACK、actual telemetry 的 transport-neutral evidence | 不拥有 command authority，也不自证设备真实执行 |
| P0.5 Command Handoff | exact `FeasibleDecision + EdgeCommandMetadata` 到 `PowerCommand` 的纯映射 | 不 tick、不传输、不执行设备 |
| P0.6 Controlled Composition | 用上述公开边界完成一个显式 cycle，并拆分 audit evidence 与 continuation | 不拥有多周期会话、scheduler 或 recovery loop |
| P0.7 Session facade | caller 显式以 one-shot continuation 接续多个 P0.6 cycle | 不自动重试、不保存/恢复 authority，也不是 background runtime |

## 3. 输入、输出与 authority

### P0.6 单周期

`ControlledEdgeCompositionInput` 接受 exact `FeasibleDecision`、exact `EdgeCommandMetadata`、P0.5 handoff
boundary、既有 P0.3 runtime、P0.4 adapter、正 duration 和非负 tolerance。P0.5 返回后，P0.6 在 P0.3 tick
前校验 source decision 与 metadata 是输入的**同一对象**，防止等值但替换过的 producer result 越过执行边界。

`ControlledEdgeCompositionResult` 分为：

- `evidence`：P0.5、P0.3 与 P0.4 的不可执行审计事实；不持有 source input、live runtime、adapter、handoff
  boundary 或 request。
- `continuation`：只保留 exact P0.3 next runtime，供新的当前 caller 发起下一 P0.6 cycle；不含 adapter、
  handoff、metadata 或 command factory，且禁止 copy/pickle/hydration。

### P0.7 session

`ControlledCompositionSession.create(ControlledCompositionSessionCreationInput(...))` 只创建 caller-owned
in-memory facade，不执行 handoff、tick、plant observation 或 transmission。`run_cycle` 只接受
`ControlledCompositionSessionCycleInput(feasible_decision, metadata, duration, tolerance_kw)` 和同一 session
当前、exact、尚未消费的 continuation。

caller **不提供 `PowerCommand`**。它只在 P0.6 内由 P0.5 从当次 decision 与 metadata 生成，并以
current-caller 语义进入 P0.3。成功时返回 immutable receipt 与下一 one-shot continuation；失败、non-admission、
unavailable/malformed facts、ACK mismatch 或 continuation misuse 都 fail closed，消费 continuation 并终止 session。

## 4. 正常 cycle：如何读一条证据链

1. caller 提供 approved `FeasibleDecision` 和新的 metadata。command ID、sequence、issued/expires time、
   requested power 与 mode 是 caller 的身份/时间事实，P0.6/P0.7 不创造或改写。
2. P0.5 handoff 从这两个 exact 输入创建 `PowerCommand`。
3. P0.3 只接受当前 tick caller 的 command；admission、safety-final action、logical execution 与
   reconciliation 由 P0.3 决定。
4. P0.4 读取 post-tick observation；若 P0.3 admitted，才形成 transmission request 并 transmission 一次，
   随后取得 ACK 和 actual telemetry observation。
5. P0.6 evidence 保留 P0.5 source/metadata、P0.3 caller/admitted/safety/reconciliation 与 P0.4 request/ACK/
   actual facts；P0.7 对 lineage 做 consumer gate，再返回 receipt 与下一 continuation。

`RuntimeLoopStep.caller_command is handoff_result.command`；若 admitted，`admitted_command` 也是该 same
command，并具 `CURRENT_CALLER` origin。这是 identity lineage，不是“字段相同即可替换”的 value comparison。

## 5. failure、fault 与 recovery

| 情形 | 合同结果 | 不允许的误读 |
| --- | --- | --- |
| P0.3 non-admission | P0.6 可留存 zero-transmission attempt；P0.7 将它 terminal fail-closed | 不是“零功率成功完成” |
| P0.4 `MISSING` / `UNAVAILABLE` | P0.6 中是 explicit audit fact；P0.7 successful cycle 要求 available，故终止 | 不是 zero power、传输成功或设备完成 |
| malformed adapter、ACK mismatch、identity/time mismatch | fail closed；不返回 success receipt | 不用替代 command、ACK power 或 history 补写 |
| session fault 或 `terminate` | submitted continuation 被消费，session 永久终态 | receipt/continuation 不能复活 session |
| recovery | caller 显式创建新 session，用新 decision、metadata 与 fresh boundary | 不是 auto-retry，绝不重放历史功率 |

P0.3 reconciliation retained actual 是 logical execution fact；P0.4 actual telemetry 是独立 adapter observation。
后者不能回写或替代前者；ACK correlation 只说明 ACK 与 request 关联，不能证明 PCS 已物理执行。

## 6. 安全边界与 no-replay

- **current caller only：**历史 trace、receipt、ACK、previous actual、safety-final request 与 serialized evidence
  都不是新 command authority。
- **one shot：**每个 P0.3 prepared execution 与 P0.7 continuation 只能按合同使用一次。
- **fresh caller facts：**同一 session 不接受重复 decision 或 metadata；跨 session continuation 也拒绝。
- **fail closed：**不能确认 lineage、availability、correlation 或 session state 时停止，不猜测、补写或重放。
- **evidence 无 authority：**evidence 不含 live adapter/handoff/input/request，不能 hydration 为 Runtime、
  Simulator、lifecycle 或 command authority。

这不是 Python 安全沙箱，也不等同于硬件权限模型；它是当前进程内对象合同的防错与可审计边界。

## 7. 代码、API 与最小验证入口

| 目的 | 路径或公开入口 |
| --- | --- |
| P0.6 composition | `edge_runtime/controlled_composition/`；`ControlledEdgeCompositionBoundary.compose()` |
| P0.7 session | `edge_runtime/controlled_composition_session/`；`ControlledCompositionSession.create()`、`run_cycle()`、`terminate()` |
| P0.3 runtime | `edge_runtime/controlled_runtime/`；`ControlledEdgeRuntime.tick()` |
| P0.4 adapter | `edge_runtime/device_adapter/`；`ResidentialDeviceAdapterBoundary` |
| P0.5 handoff | `ems_strategy/edge_command_handoff.py`；`EdgeCommandHandoffBoundary.handoff()` |
| P0.6 focused test | `tests/unit/edge_runtime/test_controlled_composition.py` |
| P0.7 focused test | `tests/unit/edge_runtime/test_controlled_composition_session.py` |

最小阅读/验证入口是 focused test，而不是手写会绕开 construction contracts 的 PowerShell 片段：

```powershell
$env:PYTHONPATH = (Get-Location).Path
pytest tests/unit/edge_runtime/test_controlled_composition.py
pytest tests/unit/edge_runtime/test_controlled_composition_session.py
```

P0.7 focused module 有 11 个 test functions，其中一个两案例参数化，故当前收集结构为 12 cases。它覆盖 creation
无副作用、两 cycle 的一次调用、fresh inputs、post-P0.6 lineage corruption、continuation isolation、
copy/pickle rejection、termination、unavailable fact 与 fresh-session recovery。此数字是候选测试文件的结构，
不是 CI 或发布结论。

## 8. 测试与 mutation 的正确阅读

mutation 的含义是“删除或替换 guard 后，相关 focused assertion 应失败”，不是生产路径自身发生过故障。
例如，删除 lineage gate 应让 corrupted producer identity assertion 失败；删除 one-shot gate 应让跨 session/
replaced continuation protection 失败；让 P0.4 actual 覆盖 P0.3 reconciliation 应让 fact-separation assertion
失败。有效 mutation 必须通过公开 composition 或 producer corruption 加独立 assertion 触发，不能人工拼装最终
失败对象或让 producer/validator 共享同一错误逻辑。

## 9. 真实系统映射（未来接口方向）

```text
cloud / offline EMS planning
  -> approved FeasibleDecision
  -> P0.5 edge command handoff
  -> P0.3 lifecycle/safety/reconciliation on an Edge Controller
  -> future PCS/BMS observations and telemetry through a P0.4-like boundary
  -> audit / ledger / validation evidence
```

这是未来接口分工图：云端或离线 EMS 负责计划与审批输入；Edge Controller 将承担 lifecycle/safety/
reconciliation 合同；未来 PCS/BMS 才会提供实物 observation、ACK 与 telemetry。当前仓库没有实现设备协议、
网络、线程、持久化、HIL、PCS/BMS 通信、DSP/STM32 固件、硬件闭环、现场控制或安全认证。

## 10. 能力边界与学习复盘

**可以学习/验证：**approved-power lineage、caller-owned metadata、P0.3/P0.4 两层事实、同步 one-shot
continuation、terminal recovery 和 evidence/authority separation。

**不能声称：**设备已收到命令、PCS 已执行、BMS 已批准、网络可靠、断电后能恢复、现场安全已认证、HIL 已完成或
可客户部署。

1. decision 是 EMS 的审批事实，command 是 P0.5 内部生成的 Edge 请求，actual telemetry 才是设备侧
   observation；三者不应混为同一事实。
2. P0.6 用一次 composition 表达跨边界 lineage；P0.7 只管理 caller 显式接续，不把它扩展成 loop。
3. fail closed 的价值在于缺少可信事实时不创建 authority；它不是对已发生 physical action 的逆转承诺。
4. P0.7 已合并 main；该教程仍不能作为产品发布、设备执行或硬件安全证明。
