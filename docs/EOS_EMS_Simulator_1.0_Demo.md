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

## Campaign F multi-day robustness CLI

运行 `python -m ems_simulator.residential_campaign_f --output-dir simulation_output_campaign_f` 可生成约一分钟的
七日 correlated/tail validation evidence。它运行 48 core、12 deterministic tail 与 6 perfect anchors，共 882
frozen daily executions。建议按 `campaign_f_summary.txt`、`campaign_f_regime_manifest.csv`、
`campaign_f_scenario_day_manifest.csv`、`campaign_f_regret_evidence.csv`、
`campaign_f_strategy_comparisons.csv` 和 SVG 的顺序审查。

拓扑为 16 个 root CSV/TXT、10 个 root SVG，以及 882 个
`executions/<regime>/<scenario>/day_<index>/<strategy>/mpc_decisions.csv`：共 908 个 deterministic、untracked files。
core 统计仅描述合成 sample；tail 不含概率权重。Campaign F 先执行 semantic validation，再验证 non-final artifacts，
写入 final summary/findings 后再验证最终 908-file topology、summary 的 frozen ordered schema、所有 root CSV 和每一
份 nested CSV 的完整内容及 SVG XML/visible mapping。每份 nested CSV 必须是 24 行、带 timezone 的一小时时序、有限
数值/合法 action 与 boolean，并逐字段对应 retained completed trajectory；删行、复制、改写 strategy/timestamp/power 或
NaN/Infinity 都会使发布失败。final contract 失败会留下包含实际 artifact counts 的 self-validating diagnostic FAIL；writer
异常也会令 CLI 非零退出，绝不会打印 PASS。D signature 含 terminal value，runner-input boundary 逐日验证 immutable
core/tail/reversal/anchor forecast 与 realized facts，CRN/core-tail 使用 exact key set 和 multiplicity。所有会计 CSV 字段为
12-decimal evidence，建议用 `1e-9` 绝对容差和解。SVG 图内以 `R/HP/HEL`、`C/T`、`S/E` 的可见短标签/legend 追溯
series；ECDF 还逐 strategy 显示排序 rank→case。它不意味着现场
概率、鲁棒优化、硬件或客户部署就绪。

Campaign F maximum summary evidence is plural: every maximum contains its value,
deterministically ordered `scenario_id`/`strategy`/`value` references and a
reference count. The normal Campaign F result has Schedule/Economic ties for all
three maxima. Float tie membership is reporting-only absolute `1e-9` (relative
zero); revision counts use exact equality. Final validation parses JSON and
recomputes the complete argmax sets directly from retained raw evidence rather
than reusing generation's maximum/tie/order/serializer helpers. Focused
mutations validate one supplied summary or nested CSV; the production gate still
scans all 882 nested files. Nested-output regression covers record
position/order, non-finite values, schema and path traceability; a non-first-row
corruption must reach final diagnostic FAIL and a nonzero CLI exit.

Generator-side common-mode regression separately covers omitted Schedule/Economic
references, reversed order, wrong scenario, extra non-maximum reference, wrong
count and malformed JSON. All seven have targeted independent-validator coverage
with zero nested scans. Omit Schedule, wrong scenario, extra non-maximum, wrong
count and malformed JSON additionally reach the real production publication
orchestration, each scanning all 882 nested files and producing diagnostic FAIL;
the tests do not synthesize the final finding or status.

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
