# Residential Edge P0.8：Adapter Conformance 领导摘要

## 状态

P0.8 已本地验证并已本地提交（`993abdf`），待最终独立发布复审和合并；尚未合并 main，也不代表 production 或 hardware readiness。

## 能力与产品价值

- 以 test-only、同步、transport-neutral harness 核对一次 caller-driven P0.7/P0.6 cycle 的 adapter transcript。
- 保留 approved decision → P0.5 handoff → P0.3 logical execution → P0.4 audit facts 的可审计 lineage。
- 将 transcript、ACK、actual、receipt 和 verdict 固定为不可执行事实，避免历史 evidence 被误用为新 command authority。
- 对顺序、重复、availability、ACK correlation 与 actual/reconciliation 差异 fail closed。

## 实际验证

P0.8 focused 9、relevant 67、Edge Runtime 221、Residential frozen 530、Campaign A–F 62、full pytest 2721 均有本地证据；user-terminal pre-commit 四 hooks exit 0，四项隔离 mutation 均被 killed。这些是代码与验证合同证据，不是物理设备结果。

## 安全边界

P0.8 不创建 command、adapter、runtime、session 或 continuation authority。ACK 不是设备执行证明；P0.4 actual 不能替代 P0.3 reconciliation。失败终止当前 P0.7 session，recovery 必须由 caller 以新 session、decision 与 metadata 显式开始。

## 仍不能做与下一阶段 gap

当前不含 protocol、network、HIL、PCS/BMS 通信、DSP/STM32、hardware control、field deployment 或安全认证。后续投入应聚焦真实 PCS/BMS 接口与安全边界、HIL、真实 telemetry/ACK 校准、故障恢复和现场验证；这些是产品化 gap，不是当前 P0.8 已交付能力。
