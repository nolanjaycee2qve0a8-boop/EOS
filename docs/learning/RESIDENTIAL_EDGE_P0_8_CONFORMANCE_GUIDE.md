# Residential Edge P0.8 Adapter Conformance 学习指南

## 1. 状态与专题必要性

P0.8 production scope 已**本地验证并已本地提交**（`993abdf`），待最终独立发布复审和合并；它尚未合并 main，不能称为 production、hardware 或 field ready。

P0.6–P0.7 指南解释了 caller-driven cycle 与 one-shot session。P0.8 增加 transcript conformance、evidence-versus-authority 与 fact separation；这些内容不能只靠旧指南的一段导航完整教学，因此需要独立专题。

## 2. 一句话目标

P0.8 是 test-only、caller-driven、同步、transport-neutral 的 conformance consumer：它用一份 ordered finite scripted transcript 核对 P0.7/P0.6 的 immutable evidence，而不是 adapter、controller 或 transport。

## 3. 架构位置

```text
approved FeasibleDecision + fresh EdgeCommandMetadata + transcript
                              │
                              ▼
                    P0.8 conformance consumer
                              │ one P0.7 run_cycle
                              ▼
P0.5 handoff → P0.3 admission/tick → P0.4 observation/transmit/ACK/actual
                              │
                              ▼
                 immutable receipt/evidence ↔ transcript comparison
                              │
                              ▼
                   audit-only AdapterConformanceVerdict
```

这些是进程内、同步的合同调用与事实比较，不表示网络发送、PCS/BMS 接收或物理执行。

## 4. 输入合同

`AdapterConformanceCycleInput` 接受 exact caller-approved `FeasibleDecision`、fresh caller-owned `EdgeCommandMetadata`、正 duration、非负 tolerance 与 `AdapterConformanceTranscript`。caller **不得**提供 `PowerCommand`；command 仍只由 P0.5 从当次 decision 与 metadata 生成。

Transcript 是有限的 scripted facts：observation、transmission、acknowledgement、actual telemetry。它不是协议日志或硬件收据。

## 5. 输出合同

`DeterministicAdapterConformanceHarness.evaluate(...)` 返回 immutable、audit-only `AdapterConformanceVerdict`。它不含 session、continuation、runtime、adapter、handoff、prepared request 或 command，也没有 factory、hydration 或 replay entry；copy、deepcopy 与 pickle 均被拒绝。

## 6. 正常流

有效 admitted transcript 的顺序是 observation → 对应 request 的一次 transmission → 具 ID/sequence/correlation 的 ACK → available actual telemetry。Harness 通过 P0.7 `run_cycle` 一次；成功路径中 P0.5 handoff 一次、P0.3 admission/tick 一次、P0.4 transmission 一次。P0.8 比较已有 evidence，不产生或发送 command。

## 7. Exact-once 的含义

这是一项逻辑调用和审计约束，不是通讯 QoS、设备幂等协议或现场 exactly-once 证明。P0.8 不拥有 scheduler、retry loop、background thread、clock service 或 durable recovery。

## 8. P0.3 与 P0.4 的两层事实

P0.3 retained actual/reconciliation 是 logical execution fact；P0.4 actual telemetry 是独立、脚本化的 adapter observation。P0.8 可以比较二者，但 P0.4 actual 不得覆盖 P0.3 reconciliation。相关 ACK 仅说明它与 request 对应，**不证明** PCS/BMS 已物理执行。

## 9. Fail-closed 失败语义

out-of-order、duplicate、malformed 或 unavailable transcript，ACK ID/sequence/correlation mismatch，actual/reconciliation mismatch，identity/time mismatch，或将 non-admission 表示为成功 transmitted cycle，均不产生 successful verdict。Harness 不猜测零功率、不补写事实、不生成替代 command。

## 10. Session 消耗与 fresh recovery

post-cycle transcript mismatch 会经 P0.7 `terminate(...)` 消耗当前 session。历史 transcript、ACK、actual、receipt 与 verdict 都不能恢复它。recovery 必须创建新 session，并由 caller 提供新 decision、fresh metadata 与新的 scripted facts；这不是 auto-retry 或 historical-power replay。

## 11. Evidence 不等于 authority

| 对象 | 可做 | 不可做 |
| --- | --- | --- |
| exact decision + metadata | 当前 caller 输入既有 handoff 合同 | 由 P0.8 复制、改写或替换 |
| P0.5/P0.3/P0.4 evidence | 留存 lineage、admission、ACK、actual 审计事实 | 反向产生 command 或执行权力 |
| transcript | 核对 scripted P0.4-style facts | 变成 adapter、protocol log 或 physical completion |
| verdict | 审计 conformance | 恢复 runtime/session/continuation/command |

这是进程内防错与可审计边界，不是 Python 安全沙箱、协议安全或硬件权限系统。

## 12. API 与代码导航

| 目的 | 路径或入口 |
| --- | --- |
| P0.8 public surface | `edge_runtime/adapter_conformance/__init__.py` |
| harness | `edge_runtime/adapter_conformance/harness.py` |
| focused test | `tests/unit/edge_runtime/test_adapter_conformance.py` |
| P0.7 session | `edge_runtime/controlled_composition_session/` |
| P0.6 composition | `edge_runtime/controlled_composition/` |
| P0.4 facts | `edge_runtime/device_adapter/` |

Public surface 是 input、transcript/fact/kind、verdict、failure error 和 deterministic harness；没有 `PowerCommand` input 或 transport import。

## 13. 最小复现入口

优先阅读真实 focused test，而不是手写绕开 construction contracts 的片段：

```powershell
$env:PYTHONPATH = (Get-Location).Path
pytest tests/unit/edge_runtime/test_adapter_conformance.py
```

其 9 个 focused cases 覆盖 normal、non-admission、order/duplicate、unavailable/ACK mismatch、fact separation、actual mismatch 后的 session consumption、audit-only verdict、fresh recovery 与 public-surface boundary。

## 14. 已验证证据如何解读

本地证据为：P0.8 focused 9、relevant 67、Edge Runtime 221、Residential frozen 530、Campaign A–F 62、full pytest 2721。P0.8 user-terminal pre-commit 的四个 hooks 已通过且 exit 0；四项隔离 mutation 均被独立 assertion killed。这些验证当前代码合同与测试保护，**不**证明真实设备、现场或 production reliability。

## 15. 真实 PCS/BMS 的未来映射

未来可把 PCS/BMS observation、transmission receipt、ACK 与 telemetry 映射到 P0.4-like facts，并以 conformance testing 检查语义、identity 与事实分离。当前没有 protocol、network、Modbus、CAN、serial、HIL、PCS/BMS 通信、DSP/STM32 固件、hardware control 或 field readiness。

## 16. 能力边界与下一阶段 gap

**已能教学/验证：**transcript fail-closed、P0.5→P0.3→P0.4 lineage、logical exact-once、两层事实、P0.7 terminal consumption 与 fresh caller recovery。

**尚不能做：**把 ACK 当物理完成、把 transcript/verdict 当 authority、恢复历史 command、连接真实设备，或声称 HIL、hardware safety、现场认证、客户部署已完成。下一阶段仅是 gap：真实 PCS/BMS 接口与安全边界、HIL、真实 telemetry/ACK 校准、故障恢复与现场验证；本文件不启动新阶段。
