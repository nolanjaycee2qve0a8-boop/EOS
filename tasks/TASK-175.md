# TASK-175 — Residential EMS Reference Demo

## 目标

TASK-175 将既有 Residential EMS 能力组合为一个确定性的 24 小时参考演示，供工程评审、验收准备和后续大规模仿真基线使用。它是集成/read-model 工作，不新增优化算法、策略或物理模型。

```text
PV / Load / perfect Forecast / TOU tariff
                    |
                    v
Schedule-aware MPC     Economic Schedule-aware MPC
                    |
                    v
Physical revision -> ControlPlan -> CurrentAction -> EMSDecision
                    |
                    v
Feasibility -> Actuation -> Simulator -> actual SOC / Grid feedback
                    |
                    v
TASK-173 DailyEconomicLedger -> TASK-168 outcome -> TASK-174 comparison
```

## 参考系统与情景

- 24 个 caller-owned、每个 1 小时的区间；初始 SOC 为 50%。
- 电池：10 kWh usable capacity，SOC 范围 20%–100%，最大充/放电功率均为 3 kW，充/放电效率均为 0.95。
- 负载曲线为确定性住宅曲线：夜间低基荷、06:00–08:00 上升、白天中等负荷、17:00–21:00 晚高峰、随后回落。
- PV 曲线夜间为零，08:00–10:00 和 14:00–17:00 存在显式 PV surplus；因此可以观察 PV 吸收、外送和 headroom 行为。
- TOU import tariff：00:00–05:00 为 0.20，日间为 0.50，18:00–21:00 为 0.90 currency/kWh；export tariff 固定为 0.20 currency/kWh。
- degradation rate 固定为 0.05 currency/kWh throughput；terminal valuation 固定为 0.85 currency/kWh。两者都是演示会计假设，而非电池化学/保修模型或控制 shadow price。

Forecast 为确定性的 caller-supplied perfect forecast。它故意服务于可重复的 reference behavior，不代表真实天气、实时价格或 forecast-error robustness。

## 复用的冻结职责

演示直接复用 TASK-151 Schedule-aware 日运行器、TASK-159 Economic Schedule-aware 日运行器、TASK-173 日经济账本和 TASK-174 比较解释器。它不会复制 opportunity schedule、headroom、economic planning、candidate planning、physical revision、Feasibility、Actuation 或 Simulator 算法。

每一后续控制周期仅使用上一小时实际 Simulator `next_state.soc` 和实际 grid power；projected SOC 从不作为实际反馈。Export 在本演示中是显式允许并按 0.20 tariff 结算的，未启用 Zero Export。

## 输出与审计

CLI：

```powershell
python -m ems_simulator.residential_reference_demo `
  --output-dir simulation_output_task175_residential_reference
```

输出目录（不纳入版本控制）包括：

- `residential_reference_timeseries.csv`
- `residential_reference_summary.csv`
- `residential_reference_economic_comparison.csv`
- `residential_reference_explanation.txt`
- `residential_power_flow.svg`
- `residential_soc.svg`
- `residential_tariff.svg`
- `residential_economic_components.svg`

CSV 逐时保留 PV、Load、两条路径的实际 Battery/Grid/SOC、tariff 和关键 economic/headroom/physical-revision flags。summary 每条路径保留能量、账本和 TASK-168 adjusted outcome。文本说明回答什么时候从电网/PV 充电、什么时候放电、SOC/电网能量、吞吐量、完整经济成本、TASK-174 ranking/主导组分，以及四个代表时段的 candidate → economics/headroom → physical revision → final action。

## 不变量与边界

参考演示验证：24 个区间、SOC 边界、充/放电功率边界、逐时 `PV + Grid - Battery = Load` 能量平衡、实际 Simulator feedback、两条 TASK-173 ledger reconciliation，以及 TASK-174 decomposition reconciliation。

TASK-175 不证明真实天气或 forecast-error robustness、真实 PCS/BMS 集成、通信可靠性、实际电池衰减经济性、真实 tariff 适用性、工业场站行为或多储能设备行为。它是 Residential EMS 1.0 的确定性 reference demo，不是最终验证活动或新的控制目标。
