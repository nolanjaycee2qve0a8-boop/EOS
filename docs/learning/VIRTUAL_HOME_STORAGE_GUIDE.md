# 虚拟家庭储能：从策略请求到虚拟执行

这是给 PCS/DSP/BMS 工程师的有限纵向教学示例，所有结果均为 **simulated**，
不是设备采集或硬件闭环。先读[有界教学合同](../../examples/virtual_home_storage/CONTRACT.md)，
再运行本例；不需要设备、网络或凭据。

## Why：为什么要分开看这些数

PV 多于负载时，SelfConsumptionStrategy 请求把盈余用于充电；负载大于 PV 且
SOC 高于储备时，请求放电补缺。策略只输出方向和非负功率 magnitude，不做物理限幅。
示例中的 approval fixture 是调用方对固定输入给出的显式教学批准，验证策略输出符合
固定预期后才绑定 FeasibleDecision。它不是完整自动生产 feasibility，不能推广为
“任意策略请求都被批准”。

下面三个充电数可以同时成立：策略请求 6 kW、fixture 批准 6 kW、安全最终允许
1.5 kW。它们描述不同层次，不能互相覆盖。BMS 降额到 1.5 kW，PCS 上限仍是
3 kW，因此冻结安全实现取更小约束。限幅场景刻意保留原请求，不把它预先改为 1.5。

## How：运行与逐步阅读

从仓库根目录，使用装有开发依赖的 Python 3.12：

```bash
python -m examples.virtual_home_storage.demo --output /tmp/eos-virtual-home-output
```

输出中文讲解，以及 `steps.json`、`steps.csv`。每行是一个固定场景的一次命令周期；
CSV 的嵌套对象是 JSON 单元格。完整输入保留在 `input`，含容量、效率、SOC、
BMS/PCS 配置、故障脚本、审批 fixture、虚拟时间和命令 metadata。
这是 source-checkout 示例，不作为 wheel 内的生产接口发布。

```text
新 EMSContext → SelfConsumptionStrategy.evaluate → 新 EMSDecision/Provenance
  → 显式 scenario approval fixture → FeasibleDecision
  → P0.7 caller session → P0.6 composition
      → P0.5 command handoff
      → P0.3 tick → P0.1 safety / P0.2 虚拟 PCS+BMS → reconciliation
      → P0.4 独立 scripted observation / transmission / ACK / actual
```

最后一行在 tick 之后发生，没有返回前面形成设备反馈闭环。示例的观察子类只调用
原实现并保留实际返回的不可执行事实；未复制控制算法，未 monkeypatch 核心。
每场景先有一次无命令的 1 秒启动 tick，然后一次 60 秒命令周期，随后显式终止
session；反例失败由 session 终止。终止 session 是结束教学调用权限，不是向物理
设备发送停止命令，也不制造额外零功率 tick。

| 场景 | PV / load kW | 策略 magnitude | command kW | safety kW | virtual actual kW | 最终 SOC |
| --- | --- | --- | --- | --- | --- | --- |
| charge | 4 / 1 | charge 3 | +3 | +3 | +3 | 50.45% |
| discharge | 1 / 4 | discharge 3 | -3 | -3 | -3 | 49.444444% |
| power_limit | 7 / 1 | charge 6 | +6 | +1.5 | +1.5 | 50.225% |
| expired | 4 / 1 | charge 3 | +3 | null（未准入） | 0 | 50% |
| ack_mismatch | 4 / 1 | charge 3 | +3 | +3 | +3 | 50.45% |

固定容量为 10 kWh、SOC 起点 50%、上下界 20–90%、充放效率均 0.9。
正号是充电，负号是放电。60 秒是 1/60 小时，3 kW 对应 AC 侧 0.05 kWh：
充电存入 0.045 kWh，除以 10 kWh 增加 0.0045 SOC；放电需从电池取出
0.05/0.9 = 1/18 kWh，SOC 减少 1/180。1.5 kW 限幅充电存入 0.0225 kWh。
测试的预期是上述手算常量，没有调用被测实现的积分公式来生成 expected。

按字段阅读：

1. `strategy_action`、`strategy_request_kw_magnitude`：真实策略输出。
2. `approval_fixture`、`approved_*`：固定场景批准，不是物理可行性证明。
3. `command`：P0.5 的符号转换及原样 metadata；`admitted` 区分是否准入。
4. BMS/PCS limits、`safety_final_kw_signed`、`safety_reasons`：安全限幅。
5. `p02_ack`、`virtual_actual_kw_signed`、SOC、`p03_reconciliation`：虚拟执行事实。
6. `p04_observation`、`p04_transmission`、`p04_ack`、`p04_actual`：独立脚本事实。
7. `stop_reason`、`receipt_returned`、`session_terminal`：本次调用如何结束。

## Tests：三个容易误读的边界

**限幅不等于 lifecycle 完成。** 限幅后 virtual actual 为 1.5 kW，但冻结 P0.1
completion 仍与原 command 6 kW 比较。P0.3 因而记录 `lifecycle_incomplete`，
runtime 进入 DEGRADED；P0.7 可以返回 receipt，因为其合同检查准入和 adapter facts，
不保证 P0.3 completion。示例在此结束，不隐藏该事实，不补偿重试。

**命令过期在准入阶段拒绝。** 虚拟 tick 从 00:00:01 开始，而反例有效期截止
00:00:00。P0.3 记录 `command_expired`，没有 safety-final、没有 P0.2 ACK、
没有 P0.4 transmission；P0.7 无成功 receipt。P0.4 仍可以读取独立脚本 ACK，
但没有 transmission 时它不是 correlated ACK，更不会授权执行。

**P0.4 ACK 失配不能撤销此前 tick。** 此例 P0.2 已接受其虚拟 ACK 并充电，
P0.3 已得到 3 kW 和 50.45% SOC；随后 P0.4 读到 `different-command`，
相关性检查抛错，session 终止，不返回 continuation。P0.4 actual 读取尚未发生，
因此 `p04_actual_read=false`、`p04_actual=null`，不能用配置值假装读取结果。

正常场景的 P0.4 actual 故意取独立起始快照：0 kW、50% SOC、00:00:01。
这不是 post-tick 测量，与 virtual actual 的差异用来说明两个事实层的来源，
它不回写 P0.3 reconciliation，也不声称对这种跨层差异做了生产诊断。

复跑 focused 测试：

```bash
python -m pytest tests/integration/test_virtual_home_storage.py -q
```

本地验证命令、初始失败与审阅结果见[验证记录](../../examples/virtual_home_storage/VALIDATION.md)。

测试还验证 exact identity、metadata 保真、重复 metadata（含 equal-but-distinct）、
重复 decision、continuation 复用、旧 provenance 配新 decision 拒绝。equal-but-distinct
metadata 会到达 P0.3 并产生第二次 logical idle tick：duplicate_command_id，未准入、
未施加命令、actual=0、SOC 不变；不能把拒绝重放说成“没有发生 tick”。新增输入事实
不能套用旧 fixture。附加 ACK dropped 测试只核对 P0.2 的模拟政策：无 ACK 则不施加
命令，功率与 SOC 变化为零；它不是第六个可选教学场景。

## Limits：可以学什么，不能推断什么

这里没有电池电化学、PWM、电流环、母线动态或硬件保护，没有 protocol、network、
HIL、真实 PCS/BMS 或部署。现实设备可以在 ACK 丢失时已经执行；accepted ACK
也不等于物理完成。不能把 P0.2 的 ACK 政策迁移为真实硬件安全结论。

JSON/CSV 只有不可执行教学事实，没有 session 恢复接口。五行不是全天调度、
MPC 或持续服务，也不是新的审计 PASS/GAP 层。冻结核心零修改。
