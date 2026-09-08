# Residential Edge P0.9：Device-Fact Readiness 领导摘要

## 状态

P0.9 是本地 production candidate，尚未 push、PR、合并或发布；本摘要是学习材料，不替代 ADR、specification 或 validation contract。

## 产品价值

- 将身份、来源、新鲜度、ACK 关联、actual presence、disconnect/reboot 与 reassessment 统一为 caller-owned PASS/GAP 审计。
- 以 explicit `as_of` 和 `max_age` 消除隐式时钟与默认新鲜度歧义。
- 保持 ACK、actual、reconciliation 与 command authority 的边界，避免把通信事实误读为物理完成。

## 实际验证

focused 14、相关 Edge 回归、Residential frozen、Campaign A–F 62、full pytest 2735、静态门禁与 pre-commit 四 hooks 均有本地终态证据；identity、future-time、ACK correlation、reassessment 和 forbidden-import 五项有效 mutation 均被 killed。这些是代码与合同证据，不是设备结果。

## 安全边界与下一步

P0.9 不生成 command，不连接 PCS/BMS，也没有 protocol、network、HIL、DSP/STM32、hardware control、field deployment 或安全认证。PASS 只表示 caller 给出的确定性证据满足 caller 的确定性语义。后续需要独立学习材料审阅，再与最终 P0.9 release audit 集成；真实设备接口、HIL、telemetry 校准和现场安全验证仍是产品化 gap。
