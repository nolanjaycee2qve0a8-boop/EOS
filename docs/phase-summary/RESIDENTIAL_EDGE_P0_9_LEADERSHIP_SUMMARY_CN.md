# Residential Edge P0.9：Device-Fact Readiness 领导摘要

## 状态

P0.9 已通过 PR #203 在 Quality checks SUCCESS 后普通合并到 repository main（`4690d47cbfa4cac0ae4eb4e9a27b722d68aa17a7`）；本摘要是学习材料，不替代 ADR、specification 或 validation contract。该仓库合并不是硬件、现场或产品发布结论。

## 产品价值

- 将身份、来源、新鲜度、ACK 关联、actual presence、disconnect/reboot 与 reassessment 统一为 caller-owned PASS/GAP 审计。
- 以 explicit `as_of` 和 `max_age` 消除隐式时钟与默认新鲜度歧义。
- 保持 ACK、actual、reconciliation 与 command authority 的边界，避免把通信事实误读为物理完成。

## 实际验证

P0.1–P0.9 focused、Residential frozen `530 passed, 62 deselected`、Campaign A–F `62 passed in 978.15s`、full pytest `2736 passed in 716.52s`、静态门禁与早期代码阶段 pre-commit 四 hooks 均有本地终态证据；identity/provenance、future-time、supplied ACK mismatch、missing six ACK fields、actual presence、reassessment 和 package-level forbidden ImportFrom alias 七项有效 mutation 均被 killed。学习示例格式修正后的隔离本地 pre-commit 因项目相对 `.pytest_cache` basetemp 的 Windows `WinError 5` 失败（pytest hook `2587 passed, 149 errors`），未计为 PASS；PR #203 的 remote Quality checks SUCCESS 独立验证了该格式修正。这些是代码与合同证据，不是设备结果。

## 安全边界与下一步

P0.9 不生成 command，不连接 PCS/BMS，也没有 protocol、network、HIL、DSP/STM32、hardware control、field deployment 或安全认证。PASS 只表示 caller 给出的确定性证据满足 caller 的确定性语义。独立学习材料审阅、本地 integration、最终审阅、PR #203 CI success 与普通 main merge 已完成；真实设备接口、HIL、telemetry 校准和现场安全验证仍是产品化 gap，并且任何后续能力须先完成 capability-gap review 与显式用户批准。
