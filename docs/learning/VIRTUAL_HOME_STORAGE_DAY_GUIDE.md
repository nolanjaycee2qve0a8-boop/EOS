# EOS 虚拟家庭储能 24 小时教学指南

这个示例把一天的固定 PV、家庭负载、分时电价和电池状态放在同一时间轴上，展示
现有 EOS 策略如何形成动作、如何经过物理约束、以及 Simulator 最终得到什么功率
和 SOC。所有输入与结果都是 **SIMULATED**，与真实硬件无关。

## 运行

在仓库根目录使用 Python 3.12：

```bash
python -m examples.virtual_home_storage_day.demo --output-dir /tmp/eos-virtual-home-day
```

主要教学输出：

- `simulated_linked_day_curve.svg`：PV、家庭负载、电池、购电、售电和 SOC 的共同
  00–23 小时时间轴。
- `simulated_hourly_decisions_zh.csv/json`：24 行逐小时机器可读记录，包含策略候选、
  EMSDecision、FeasibleDecision、Actuation、Simulator actual、SOC、价格作用和账本。
- `simulated_key_events_zh.txt`：低价充电、PV 充电、高价放电和最低 SOC 修订的中文
  why → constraints → result。
- `simulated_daily_summary_zh.txt`：能量、成本、假设和边界。
- `reference/`：既有 `residential_reference_demo` 原始输出，保留 Schedule/Economic
  两条路径、英文解释和拆分曲线，便于追溯。

## 实际复用的链路

包装层只调用一次现有 `run_residential_reference_demo`，教学主视图读取其 Economic
路径的完成事实：

```text
固定 PV / Load / Tariff + 实际 SOC
→ caller-owned perfect Forecast horizon
→ 现有 Economic multi-opportunity MPC / Strategy
→ CurrentAction → EMSDecision → DecisionProvenance
→ FeasibleDecision → ActuationHandoff
→ Simulator actual power / Grid balance / next SOC
→ 现有 Economic ledger
→ 中文逐小时教学视图
```

这里的 `Actuation` 是 Simulator 输入，不是 Edge `PowerCommand`，更不是 PCS/BMS
设备命令。PR #220 的五场景 Edge 教学例继续独立存在；本例不把 24 个小时接成
P0.7 session，不建立虚假的设备闭环。

## 固定虚拟输入与单位

日期为 2026-02-01 UTC，24 个连续步，每步 1 小时。输入直接复用现有 Residential
EMS 1.0 reference fixture：

- 电池 usable capacity 10 kWh，初始 SOC 50%，规划范围 20%–100%；
- 最大充/放电功率均为 3 kW，充/放效率均为 95%；
- 低价 0.20 元/kWh（00–05），普通 0.50（06–17、22–23），高价 0.90
  （18–21）；
- 出口结算 0.20 元/kWh，吞吐退化费 0.05 元/kWh，终端估值 0.85 元/kWh；
- PV、负载与未来电价均是固定 perfect forecast，不来自天气或设备采集。

功率单位是 kW，能量单位是 kWh，SOC 是 0–1 fraction。电池正功率表示充电，负
功率表示放电；原始电网正功率表示购电、负功率表示售电。联动图将 signed grid
拆成非负的“购电”和“售电”曲线，CSV/JSON 同时保留 signed 原值。

每步恰好 1 小时，所以购售电能量等于相应功率乘以 1 h。电池 SOC 手算为：

```text
充电：SOC_after = SOC_before + P_charge × 1h × 0.95 / 10kWh
放电：SOC_after = SOC_before + P_discharge × 1h / 0.95 / 10kWh
```

放电功率为负，因此第二式自然降低 SOC。实际进口成本是每小时购电 kWh 乘该小时
进口价；实际出口收益使用固定 0.20；退化成本使用实际电池吞吐乘 0.05。

## 如何读四个关键事件

| 时间 | 为什么 | 现有约束/链路 | 虚拟结果 |
| --- | --- | --- | --- |
| 00:00 | 无 PV，电价 0.20；Economic gate 判定低价电网充电有正经济价值 | headroom 允许 1.022438 kW，无物理修订 | 电池 +1.022438 kW，电网购电 1.822438 kW，SOC 50%→59.7132% |
| 08:00 | PV 2.0 > 负载 0.8，1.2 kW 盈余用于充电 | PV 盈余动作绕过低价电网充电 gate | 电池 +1.2 kW，电网 0，SOC 增加 11.4 个百分点 |
| 18:00 | 电价 0.90，负载 2.0 且无 PV | 放电动作绕过低价充电 gate；功率/SOC 均可行 | 电池 −2.0 kW，电网 0，SOC 100%→78.9474% |
| 21:00 | 负载缺口候选放电 1.8 kW | 1.8 kW 会越过 20% 最低 SOC，现有物理层以 `min_soc_limit` 修订 | 最终/approved/actuation/actual 均为 −0.9 kW，仍购电 0.9 kW，SOC 正好 20% |

“策略 request → approved → actuation → actual” 数值相等时，也仍是四个不同事实层。
逐小时记录保留 exact identity 测试，不能用后层结果反向冒充前层输入。

## 电价到底参与了什么

本例使用的 Economic 路径确实读取价格，但它的作用有边界：

1. 在无 PV 盈余的低价候选时段，现有 Economic gate 根据当前价、未来价和效率
   判断有多少电网充电具有经济支持，并受 headroom 限制。
2. PV 盈余充电、放电与 idle 不经过这个“低价电网充电”经济 gate。
3. 所有完成时段的实际进口电量随后按实际小时进口价进入 ledger。

本固定 reference 中 Economic 与 Schedule 两路径结果相同，因此不能宣称 Economic
路径带来额外节省。图中电价不是凭空制造的“优化收益”。出口价、退化费率和终端
估值也是 demo 会计假设；终端估值不是控制 shadow price。

## 日汇总与来源

当前固定路径的已验证结果：负载 27.1 kWh、PV 14.3 kWh、购电约 13.122438
kWh、售电约 2.659280 kWh、电池吞吐约 12.863158 kWh，最终 SOC 20%。实际进口
成本约 5.174488，出口收益约 0.531856，退化成本约 0.643158，实际净成本约
5.285789。数值来自既有完成 trace 和 ledger，不由教学包装层重新计算生产事实。

输入、runner、账本和既有图表来源分别位于：

- `ems_simulator/residential_reference_demo.py`
- `ems_simulator/economic_multi_opportunity_explainable_mpc_daily.py`
- `ems_simulator/economic_ledger.py`
- `ems_simulator/economic_schedule_aware_comparison_demo.py`

既有 `docs/EOS_EMS_Simulator_1.0_Demo.md` 还记录 Campaign C 的 forecast/realized
误差、Campaign D 的多日 SOC，以及 Campaign E/F 的抽样与机制研究。本例不复制
这些报告，也不把 perfect forecast 日误称为误差鲁棒性验证。

## 能力边界

本例不包含真实天气、真实电价、现场测量、实物 PCS/BMS、协议、网络、HIL、PWM、
电流环、母线动态、硬件保护、实时循环、凭据或部署。静态 SVG/CSV/JSON 不是设备
telemetry。只有用户以后单独启动实物阶段，才会讨论真实设备边界；本批不为该阶段
预留或暗中增加控制能力。

范围合同见 [24 小时教学合同](../../examples/virtual_home_storage_day/CONTRACT.md)。
