# Residential Edge P0.12：设备事实—命令关联连续性审计

## 管理层摘要

P0.12 为现有 Edge 审计链增加一个小而可验证的能力：在一个明确、有限的 caller 输入集合中，核对设备事实与命令关联是否持续一致。它建立在 P0.10 lifecycle audit 和 P0.11 single-member correlation 之上，但不改变控制、优化、模拟或设备通信。

## 已证明的内容

- 每个有效 member 恰好经过一次 P0.11 审计。
- P0.11 GAP、历史/错误 member、scope mismatch、重复 identity、时间或 sequence 退化都会 fail closed。
- assessment 是 immutable audit evidence，不携带 command、runtime、adapter 或 device authority。
- 验证覆盖 focused、Edge Runtime、Residential frozen、Campaign A–F、full pytest、静态检查、pre-commit 与八项 mutation；PR #215 已合并，Quality checks 为 SUCCESS，main 为 `ce37c92a5daa33a588a2a33e721162f595212553`。

## 不应过度解读

PASS 不表示 command transmission、ACK physical completion、actual device execution、PCS/BMS 连接、硬件安全或现场部署准备。P0.12 没有 protocol、network、thread、persistence、HIL 或 hardware control。

## 当前状态与下一步

本文件保留候选阶段的管理记录；P0.12 已实施、验证并随 PR #215 合并，当前 active stage 为 NONE。合并不代表 command/runtime/device/adapter authority，也不代表 protocol、network、HIL、hardware、field 或产品发布能力。任何后续阶段均须新的 gap review 与明确用户授权；若未来进入产品化，应以真实 telemetry、设备协议、故障模型和 HIL 证据验证，而不是把本审计合同当作设备认证。
