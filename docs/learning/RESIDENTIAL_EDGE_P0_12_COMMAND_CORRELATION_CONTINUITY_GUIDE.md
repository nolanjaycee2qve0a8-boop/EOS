# Residential Edge P0.12：Device-Fact Command Correlation Continuity Audit

## 目的与边界

P0.12 是本地候选、test-only 的 audit contract。它读取 caller 一次性提交的有限 P0.11 inputs，输出 immutable PASS/GAP assessment；不创建、传输、恢复或 replay command，也不接触 runtime、adapter、transport 或设备。

## 输入、输出与最小调用

输入是 `DeviceFactCommandCorrelationContinuityInput`：唯一 assessment identity、caller-provided `assessment_as_of`、`maximum_age`、明确 scope 和至少两个 members。scope 声明 transmission origin 与 P0.11 source/epoch relationship。输出只含 assessment identity、as-of、status 和 findings。

```python
assessment = DeterministicDeviceFactCommandCorrelationContinuityAuditor().evaluate(
    caller_owned_input
)
assert assessment.status in {
    DeviceFactCommandCorrelationContinuityStatus.PASS,
    DeviceFactCommandCorrelationContinuityStatus.GAP,
}
```

PASS 仅说明这些输入符合此审计合同；不说明 command 已发送、ACK 已物理完成、actual 已执行，或设备可用。

## P0.10、P0.11 与 P0.12

- P0.10 审计 device-fact lifecycle continuity。
- P0.11 审计一个 device fact 与一个 command 的 correlation。
- P0.12 不复制两者；它逐成员调用 P0.11，再审计一组 members 的 cross-member continuity。

历史 P0.11 assessment 不是新 member；P0.11 GAP 不能由后续 actual、ACK 或另一个 member 修复。P0.3 reconciliation、P0.4 actual telemetry 与 ACK 仍属于不同事实层。

## 失败、authority 与测试阅读

scope mismatch、重复 assessment/transmission/actual identity、非严格 sequence/time、stale/future time、malformed member 和 P0.11 GAP 都输出 GAP。assessment 不保留 input、member、runtime、adapter、session、continuation、transmission 或 actual authority，因此可以作为审计事实保存，却不能 hydration 或 replay execution。

focused test 位于 `tests/unit/edge_runtime/test_device_fact_command_correlation_continuity.py`。mutation evidence 分别删除 P0.11 GAP、scope、identity、ordering、historical、forbidden import 与 inert-output guards；每项都会使相应 assertion 失败。它们说明测试能够发现语义退化，不是硬件安全认证。

## 现实系统映射

未来的 PCS/BMS/Edge telemetry 可以把自己的事实整理为 caller-owned immutable inputs，再由 P0.11/P0.12 审计一致性。该映射不意味着目前已有 CAN、Modbus、network、protocol、thread、HIL、hardware integration 或现场控制能力。
