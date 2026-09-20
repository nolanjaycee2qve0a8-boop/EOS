# Residential Edge P0.11 命令关联审计指南

> PR #211 已合并的 audit-only 合同。它不是 command transmission、physical completion 或设备能力声明。

## 一句话

P0.11 审计一组 caller-owned inert facts 是否与显式 source/epoch relationship 一致。

## 最小流程

```python
auditor = DeterministicDeviceFactCommandCorrelationAuditor()
assessment = auditor.evaluate(caller_owned_input)
```

输入由 transmission identity、ACK observation、actual observation、relationship、assessment
identity/as-of 组成；输出仅为 immutable `PASS` 或 `GAP` findings。relationship 必须显式声明，
不能由相等字符串推断。

## 如何阅读结果

- `PASS`：有限 caller facts 满足本审计规则。
- `GAP`：ACK/actual unavailable、身份/sequence/origin/time 不匹配、关系缺失或冲突、或历史
  evidence 重用。
- ACK 不证明 physical completion；actual 不替代 P0.3 reconciliation。

## 边界与测试

没有 command、runtime、adapter、session、continuation、transport、协议或硬件 authority。
focused 20 tests 与 7 项 mutation 覆盖 source/epoch、relationship、ACK correlation、availability、
actual separation、history replay 和 ImportFrom alias。未来 PCS/BMS/EMS/Edge 可提供事实，仍须另行
实现可信通信、时间治理、HIL 与现场验证。

PR #211 合并 SHA 为 `1aedd2df8cee8bd91ba772dbec80b04eb5a91c6c`，最终 head
`c040d9ef237a01ba9250ae51f2ccb4508d474c32` 的 `Quality checks` 为 SUCCESS。首次 CI 的
Ruff UP038 不是 PASS；其后仅作语义等价的 Python 3.12 兼容修复。合并不授权真实通信、
硬件控制或现场使用。
