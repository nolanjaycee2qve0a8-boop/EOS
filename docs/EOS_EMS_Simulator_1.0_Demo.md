# EOS EMS Simulator 1.0 Demo

## 概览

该 Demo 是 EOS 第一个可直接运行的 24 小时家庭光储仿真示例。它复用已冻结的
Daily input、PV/Load models、Battery physics、Grid balance、24-hour runner、CSV 与 SVG
exporter，不增加新的 Runtime 或控制系统。

Demo strategy 仅用于验证 simulator：

```text
PV surplus      -> request Battery charging
PV insufficient -> request Battery discharging when SOC is available
```

Battery physics 仍负责 actual power、efficiency、power limits 和 SOC protection。该规则
不是 MPC、Optimization、AI 或最终 EMS strategy。

## 场景

场景固定包含：

- 2026-01-01 UTC 的 24 个连续 hourly steps；
- 典型白天发电的 24-hour PV profile；
- 包含早晚负荷峰值的 24-hour household Load profile；
- caller-supplied Tariff profile；
- 10 kWh Battery；
- 最大充电/放电功率各 3 kW；
- charge/discharge efficiency 均为 0.95；
- initial SOC 0.50；
- reserve SOC 0.20。

所有时间和 profile values 都是显式常量。Demo 不读取 clock、不访问设备、不做 forecast。

## 如何运行

在仓库根目录安装开发依赖后执行：

```powershell
python -m ems_simulator.demo --output-dir simulation_output
```

如果省略 `--output-dir`，默认写入仓库当前目录下的 `simulation_output`。

Python 调用方式：

```python
from pathlib import Path

from ems_simulator.demo import run_demo

execution = run_demo(Path("simulation_output"))
```

## Residential Simulation Validation Campaigns

在包含相应 Campaign 模块的修订中，可运行下面两条 post-freeze validation/reporting 命令：

```powershell
python -m ems_simulator.residential_campaign_c --output-dir simulation_output_campaign_c
python -m ems_simulator.residential_campaign_d --output-dir simulation_output_campaign_d
python -m ems_simulator.residential_campaign_e --output-dir simulation_output_campaign_e
```

Campaign E 使用固定 seed `20260817` 对三个 realized environments 各构造 64 个 caller-owned 合成 forecast
samples，并分别运行冻结的 Schedule/Economic daily paths。它不改变 demo 或控制逻辑；输出应优先审查
`campaign_e_summary.txt`、`campaign_e_sample_manifest.csv`、`campaign_e_regret_evidence.csv` 和每环境的 ECDF。

`campaign_e_sample_manifest.csv` 同时保存 realized source fingerprint、keyed transformation 参数、实际生成的
forecast PV/load/tariff SHA-256 fingerprint 和 labelled combined fingerprint。profile fingerprint 是 caller-order、
逗号分隔、固定六位小数的 evidence representation；signed zero 统一为 `0.000000`，不承诺识别六位以后差异，
也不参与控制或优化。hourly evidence 分为 9,216 行的
sampled trace 与 144 行的 retained perfect-anchor trace；后者只读取已完成的 Simulator trace，不会重跑 anchor，
也不会进入 sampled ECDF。
其中 regret 是 sampled path 相对同环境同策略 perfect anchor 的差，battery-power divergence 来自 Simulator
`actual_power_kw`，不是 planning request。该样本集是可复现的工程刻画，不是现场概率、weather forecast 或生产
可靠性认证。

两者在终端打印 `PASS` 或 `FAIL`；输出目录均为 deterministic、untracked evidence，不应提交到仓库。
Campaign C 优先查看 `campaign_c_summary.txt`、`campaign_c_forecast_errors.csv`、
`campaign_c_anchor_regret.csv` 与 `executed_battery_power_divergence.svg`，重点是 forecast error 如何穿过
冻结 planning path 并与 Simulator 的 realized execution 分离。Campaign D 优先查看 `campaign_d_summary.txt`、
`campaign_d_continuity.csv`、`campaign_d_path_summaries.csv` 与 `carry_continuity.svg`，重点是多日 actual
SOC carry、timestamp continuity 与 terminal value 只在 horizon end 计入一次。

Campaign C 已作为合并后的 validation evidence；Campaign D 在本次文档同步时仍是当前已审查分支的本地实现，
合并前不应当作 main 的能力。两者都不替代基础 Demo，也不验证真实 hardware、通信或 production runtime。

## 输出文件

### simulation_result.csv

包含 24 个 caller-ordered rows：

```text
timestamp,pv_power_kw,load_power_kw,battery_power_kw,grid_power_kw,soc
```

- Battery power 正值为 charging，负值为 discharging。
- Grid power 正值为 import，负值为 export。
- SOC 是该 step 完成后的 Battery next-state SOC。

### power_curve.svg

同时展示 PV、Load、Battery 与 Grid power。SVG 是 deterministic text artifact，可由浏览器
或工程文档工具直接打开。

### soc_curve.svg

展示 24 个 step 完成后的 Battery SOC。

### daily_summary.txt

包含：

- `pv_energy_kwh`；
- `load_energy_kwh`；
- `battery_throughput_kwh`；
- `grid_import_energy_kwh`；
- `grid_export_energy_kwh`。

## Determinism 与 identity

同一版本的 Demo 每次构造相同显式 scenario facts，并产生 byte-identical CSV、SVG 和 summary
content。每一次 execution 仍创建独立 immutable evidence graph：source input、simulation result、
export artifact 之间使用 exact identity 连接，不通过 copy、serialization 或 value-only lineage。

## Non-goals

Demo 不包含 MPC、Optimization、AI、Forecast、Runtime、Scheduler、Device、Cloud、PCS/BMS
control、Command 或 real-time monitoring。它验证 Simulator 1.0 的应用链路，不代表生产 EMS
控制器。
