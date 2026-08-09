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
