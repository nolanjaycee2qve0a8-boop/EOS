# Residential Edge P0.13：显式跨 scope 交接审计学习指南

P0.13 已通过 [PR #218](https://github.com/nolanjaycee2qve0a8-boop/EOS/pull/218) squash merge，
实现 main 为 `c7ee7ffdfb20b9133c5955c6921233cfccaf5fe5`。本指南是该实现的文档收尾候选；
准确来源、历史失败和审核口径见[实施证据](../validation/RESIDENTIAL_EDGE_P0_13_IMPLEMENTATION_EVIDENCE.md#最终合并与审核摘要2026-10-02)。

## 为什么需要 P0.13

一个 scope 内部一致，不能证明它与另一个 scope 衔接一致。调用者需要把“哪些事实交给哪些事实、
允许怎样的序号与时间变化”显式写出，审计器才有可检验的声明，不能靠历史 PASS 补推。

| 阶段 | 解决的问题 | 不能替代的事实 |
| --- | --- | --- |
| P0.10 lifecycle | 显式设备事实的生命周期连续性 | source/epoch 改变本身不是 disconnect/reboot/reconnect |
| P0.11 single correlation | 单个 transmission/ACK/actual 的关联 | ACK 不等于物理完成，actual 不替代 P0.3 reconciliation |
| P0.12 scope internal | 一个声明 scope 内的有限 P0.11 成员连续性 | 一个 scope 的 PASS 不证明跨 scope 交接 |
| P0.13 cross scope | 两个 raw-input scopes 与显式 handoff declaration 的一致性 | 不合并 scope，不提供执行或跨调用来源证明 |

P0.13 的 handoff 是声明性审计关系，没有传输、命令转交或 continuation 消费行为。

## 怎么做：保留原始事实，逐层审计

1. 调用者提供恰好两份不同的 `DeviceFactCommandCorrelationScopeFacts`，每份 `continuity_input`
   持有精确 P0.12 `DeviceFactCommandCorrelationContinuityInput`：有序有限 P0.11 raw inputs、
   原始 scope declaration、assessment identity、`assessment_as_of` 和 `maximum_age`。
2. P0.13 先检查惰性精确类型表示。每个结构有效的 scope 原对象交给冻结 P0.12 auditor **恰好一次**；
   一侧结构无效或 P0.12 GAP 不阻止另一结构有效侧的一次审计，但阻止进入交接判断。
   结构无效侧不委托；不能把历史 P0.12 assessment、序列化结果或摘要当作 raw inputs。
3. 两侧都 PASS 后，显式 declaration 对照两个原始 scope 的 identity、origin、完整六字段 source/epoch
   relationship，以及前 scope 实际最后成员与后 scope 实际首成员的 identity、sequence、assessment time。
   本版本只接受 `member_identity_relationship="distinct"`；assessment、transmission、actual identity
   各自在其 domain 内核对唯一性，不混用不同 identity domain。
4. 检查严格递增且精确声明的 sequence/time advance、完整跨 scope 时间范围、所有成员与两份 P0.12
   assessment as_of 相对新 P0.13 as_of 的 freshness。无默认时钟、默认容差、排序、补值或自动合并。
5. 输出仅有新 assessment identity、as_of、PASS/GAP 与不可变 findings；不保留 raw input 或前置活对象。
   “惰性（inert）”指不能执行/恢复 authority，不是延迟执行。

字段与公共类型见[contracts.py](../../edge_runtime/device_fact_command_correlation_scope_handoff/contracts.py)，
实际 gate 见[evaluator.py](../../edge_runtime/device_fact_command_correlation_scope_handoff/evaluator.py)。
有效外层 envelope 中的非法嵌套事实返回 GAP；错误外层类型直接 TypeError，
构造时缺失/非法 identity、as_of、maximum_age 等可能 TypeError/ValueError，不能为了返回 GAP 捏造 identity 或时钟。

### 显式 10 → 12：跳号不是自动推断

假定两个 scope 分别为 `[9, 10]` 与 `[12, 13]`，其余 identity/time/freshness 等条件均合法：

| declaration | 结果及原因 |
| --- | --- |
| 实际 terminal=10、initial=12，`sequence_advance=2` | 可以 PASS；严格向前且差值与声明完全相等 |
| 同样实际边界，`sequence_advance=1` 或缺失 | GAP；不补成默认 +1，也不自动推断 +2 |
| declaration 指向前 scope 第一项或后 scope 最后一项 | GAP；必须是实际 terminal/initial，不能选择看起来合适的成员 |

这里的序号一致性不证明编号 11 的命令存在、已发送、丢失或已经执行。

### DST 反例：看起来晚了，实际可能更早

纽约回拨日的同一小时出现两次。`01:30 fold=1` 是 06:30 UTC，`01:45 fold=0` 却是 05:45 UTC；
墙上时间增加 15 分钟，绝对时刻倒退 45 分钟，必须拒绝。以下是可单独运行的时间教学例子，
不是 auditor 实现，也不替换其整数微秒坐标算法：

```python
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

zone = ZoneInfo("America/New_York")
terminal = datetime(2025, 11, 2, 1, 30, tzinfo=zone, fold=1)
initial = datetime(2025, 11, 2, 1, 45, tzinfo=zone, fold=0)
assert initial - terminal == timedelta(minutes=15)
assert initial.astimezone(UTC) - terminal.astimezone(UTC) == timedelta(minutes=-45)
```

即使真实 terminal→initial 绝对时间向前，也还要验证
`max(previous member instants) < min(next member instants)`。DST 下 P0.12 的冻结 scope 内语义
可能允许内部绝对时间倒序；只看首尾就会漏掉完整范围交叠。P0.13 只读扫描范围，不排序或重审 P0.12 内部规则；
两范围确实分离的合法控制仍保留。freshness 也按绝对时刻核验，年龄等于 maximum_age 可通过。

初审还发现自定义 tzinfo 可以暗藏 raw/authority，tuple 或 float 等子类可绕过惰性表示边界。
修复后先核对精确类型，再使用可信标准时间行为；拒绝自定义时区及不透明的文件流 ZoneInfo，
不调用不可信 hook 去“清洗”事实。合法 UTC、固定偏移、常规 ZoneInfo 和 fold 正向交接仍有控制例。

## 怎么验：读 gate，也读会失败的反例

[现有 focused tests](../../tests/unit/edge_runtime/test_device_fact_command_correlation_scope_handoff.py)
中的 `request()` 明确构造两份 raw requests 与 10→12 声明，未人工伪造最终 PASS。
在仓库根目录、已具备开发依赖的 Python 3.12 环境，可做以下四项短示例核验：

```bash
python -m pytest -q \
  tests/unit/edge_runtime/test_device_fact_command_correlation_scope_handoff.py::test_real_raw_scopes_pass_with_explicit_10_to_12_advance \
  tests/unit/edge_runtime/test_device_fact_command_correlation_scope_handoff.py::test_each_scope_delegates_once_preserving_exact_input \
  tests/unit/edge_runtime/test_device_fact_command_correlation_scope_handoff.py::test_review_dst_backwards_handoff_is_gap \
  tests/unit/edge_runtime/test_device_fact_command_correlation_scope_handoff.py::test_disjoint_ranges_preserve_frozen_scope_internal_semantics
```

这四项只核验教学入口，不能代替完整证据。已合并证据记录作者 full **2986 PASS**，
Ruff/format/mypy PASS，本地 pytest hook **Skipped**（复用同 source hash 全量）。公开 PR 记录
最终独立 KEEP、250 focused/predecessor、28 prior controls、3 microsecond controls PASS，
及 28 semantic mutation 的真实断言独立重放击杀；独立上下文/副本共用 executor，不是独立机器。
初审 REVISE、复审完整范围问题、原脚本 TypeError 预期变化与 -15 中断全部保留，不能回填成通过。
主线 [CI API success](https://github.com/nolanjaycee2qve0a8-boop/EOS/actions/runs/36997610237)
不提供本轮未下载日志中的测试数量。

## 能力限制与交接

无 provenance registry、跨调用 state 或 persistence，故不能证明 raw inputs 来自当前调用者，
不能证明跨调用唯一性或 scope reuse，也不能识别人为重新包装成合法 raw inputs 的历史事实。
重复合法调用的确定性结果不授权 replay。frozen dataclass 也不是抵御进程内任意篡改的安全沙箱。

软件 PASS 不等于 PCS/BMS、HIL、硬件安全或 field proof；没有 command/device/runtime/adapter/transport、
continuation、restore/replay authority。本文不增加 Demo 控制、协议、网络、线程、调度、持久化、设备或部署能力。
后续只待文档独立复核与主对话处理本地候选；未启动 P0.14 或第七册。
[领导摘要](../phase-summary/RESIDENTIAL_EDGE_P0_13_LEADERSHIP_SUMMARY_CN.md)说明已完成价值与未闭合门禁。
