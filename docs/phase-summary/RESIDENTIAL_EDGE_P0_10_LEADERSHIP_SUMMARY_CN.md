# Residential Edge P0.10 生命周期连续性候选：领导摘要

> **状态：本地候选，未提交生产实现、未发布、未合并。** 本页描述预期价值与边界，不代表已经交付的设备能力。

## 新增价值

P0.10 拟把单时刻 device-fact readiness 扩展为对有限事实序列的连续性审计：明确识别断连、重启、身份 epoch 变化、时间断点、identity reuse 与不合规 reconnect。这样可让“数据是否连续、为何不能连续”形成可审计的 `PASS/GAP` 结论，而不是被隐式忽略。

## 安全与 authority 边界

它是 caller-driven、deterministic、immutable、audit-only profile。历史 assessment、GAP、ACK、actual telemetry 都不能恢复 command、runtime、lifecycle、adapter 或 replay authority。缺失、未知或矛盾事实按 fail-closed 规则形成显式 `GAP`；这不等同于物理停机、设备安全确认或实际动作完成。

## 实际验证（候选范围）

候选验证关注正常连续性、六类 lifecycle transition、identity/time/source 关系、reconnect 前提、ACK/actual 缺失、历史 evidence 再输入和禁止 transport 依赖。验证对象是确定性、调用方提供的事实与审计规则；不把 synthetic/测试 evidence 写成现场可靠性或硬件认证。

## 仍不能做

P0.10 不连接 PCS/BMS，也不实现 CAN、Modbus、HTTP、网络、轮询、线程、scheduler、持久化、HIL、STM32/DSP、设备控制、现场安全认证或客户部署。它不改变冻结 Residential EMS 1.0 策略、MPC、Feasibility、Actuation、Simulator、经济核算或 Campaign A–F 数值。

## 下一阶段

在候选合同经过独立审查并获授权后，下一步应先决定是否把 P0.10 作为受限的审计能力推进；真实产品化仍需另行投入可信设备接口、时间/身份治理、故障恢复、PCS/BMS 通信、安全边界、HIL 与现场验证。任何这类工作都必须独立立项，不能由 P0.10 audit evidence 自动推导为已具备。
