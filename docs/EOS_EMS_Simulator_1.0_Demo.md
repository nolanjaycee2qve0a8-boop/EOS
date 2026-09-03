# EOS EMS Simulator 1.0 Demo

## Edge P0.3 focused runtime prototype

`python -m pytest tests/unit/edge_runtime/test_controlled_runtime.py -q` 验证 caller-driven
启动/恢复 observation、READY-start admission、state matrix、readiness 输入、命令 identity/
sequence、ACK/actual 最小 fail-closed 行为与 fault-clear no-replay；不连接 PCS/BMS、STM32/DSP
或 HIL。P0.3 每 tick 准备一个 P0.2 snapshot 并 execute 一次；本命令不证明真实设备协议时序。
每个 admitted command 只能来自当前 caller；`tick(None)` 不会从 trace、lifecycle、ACK、actual
或 READY recovery 自动重放、重试、重新编号或恢复上一条功率。
Stage 2B 同时验证 request/safety-final/ACK/expected-actual/actual-telemetry 五层事实、
compound reconciliation 以及严格 audit-trace JSON；trace 不能 hydration 为 Runtime 或设备
authority，也不实现 restart recovery。

> **P0.2 device-simulator contract test:**
>
> ```powershell
> pytest tests/unit/edge_runtime/test_device_simulator.py
> ```
>
> 该测试显式推进 virtual clock，覆盖虚拟 PCS/BMS 故障、P0.1 safety、ACK、actual telemetry
> 与 lifecycle refusal/completion。它不连接真实设备，不生成 Runtime loop，也不应被解释为
> HIL 或硬件认证。
> P0.2 只应用即时 accepted、未过期 ACK；reject/drop/delay 均不会在该 step 产生 command
> actual power 或 SOC 变化。其 fault schedule 在 step 起点采样，并非连续时间设备模型。
> 这是保守 simulator policy，不表示真实 PCS 在 ACK 丢失或迟到时必然未执行；未来 Runtime 仍须
> 以 actual telemetry 为执行事实并进行 production-grade reconciliation，P0.2 未实现该能力。

> **P0.1 Edge contracts test:** the following is a contract-only test command,
> not a real-device CLI. It does not create a loop, poll telemetry or transmit
> a command:
>
> ```powershell
> pytest tests/unit/edge_runtime/test_edge_runtime_contracts.py
> ```
>
> `PowerCommand`, ACK and `TelemetrySnapshot` are future adapter-facing facts;
> Simulator output remains a simulation fact and no PCS/BMS/CAN/RS485/Modbus
> protocol is implemented by this repository entry.
>
> P0.1 test observes contracts only: BMS/PCS capability is derived inside the
> safety evaluator, `READY` plus complete recovery facts are required for a new
> active request, and lifecycle completion requires authoritative actual-power
> telemetry observed after execution starts and before command expiry. Parsed
> lifecycle records are audit evidence only, not durable command restoration.
> A `COMPLETED` record without that actual completion evidence is invalid; a
> supersede successor must be above the book-global sequence maximum and failed
> replacement leaves no partial lifecycle write. The transition matrix is
> enforced internally through specialized methods, not a generic transition API.
> It neither polls nor controls a device; `SAFE_IDLE` is a software request,
> not a hardware-safe confirmation.

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

Campaign C/D 均已作为合并后的 validation evidence，并由后续 E/F 复用；它们都不替代基础 Demo，也不验证
真实 hardware、通信或 production runtime。

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

## Residential Validation Campaign A–F CLI 索引

Campaign A–F 是冻结 Residential EMS 1.0 的验证/报告工具，不改变基础 Demo 或生产控制。所有输出目录
均为 deterministic generated evidence，必须保持未跟踪；不要把 `simulation_output_campaign_*` 提交到仓库。

| Campaign | CLI | 主要输出目录 | 推荐首先阅读 |
| --- | --- | --- | --- |
| A | `python -m ems_simulator.residential_campaign_a --output-dir simulation_output_campaign_a` | `simulation_output_campaign_a/` | `campaign_summary.txt`、findings、KPI/comparison CSV |
| B | `python -m ems_simulator.residential_campaign_b --output-dir simulation_output_campaign_b` | `simulation_output_campaign_b/` | B1–B4 summary、swept-input SVG、findings |
| C | `python -m ems_simulator.residential_campaign_c --output-dir simulation_output_campaign_c` | `simulation_output_campaign_c/` | anchor-regret CSV、actual-power divergence evidence |
| D | `python -m ems_simulator.residential_campaign_d --output-dir simulation_output_campaign_d` | `simulation_output_campaign_d/` | carry continuity、aggregate accounting、multi-day summary |
| E | `python -m ems_simulator.residential_campaign_e --output-dir simulation_output_campaign_e` | `simulation_output_campaign_e/` | summary、sample manifest、regret evidence、ECDF |
| F | `python -m ems_simulator.residential_campaign_f --output-dir simulation_output_campaign_f` | `simulation_output_campaign_f/` | final summary/findings、manifest、regret/comparison CSV、publication gate evidence |

推荐阅读顺序是 A（冻结基准）→ B（边界）→ C（forecast/realized 分离）→ D（多日 SOC 与
terminal-once accounting）→ E（independent fixed-seed samples）→ F（correlated multi-day core/tail 与
publication contract）。统一口径见
`docs/validation/RESIDENTIAL_VALIDATION_A_F_SUMMARY.md`。

### PASS / FAIL 的真实含义与证据受众

`PASS` 表示对应 Campaign 的既定 hard acceptance 或最终 publication evidence contract 已通过；它不表示
真实天气准确、HIL 完成、硬件安全、生产可靠性或客户部署就绪。`FAIL` 表示该 Campaign 的既定合同不满足，
应保留 diagnostic evidence 并进行审查，而不是由报告层修改控制。

- **开发调试**：scenario/sample manifest、hourly trace、nested `mpc_decisions.csv`、局部 SVG。
- **审计复核**：summary/findings、ledger/comparison/anchor-regret CSV、F 的 final publication contract。
- **管理层展示**：每 Campaign summary、核心 KPI/比较 SVG、统一 A–F 收口报告；不可用单一图或
  ranking 取代范围和限制说明。

## Edge P0.5 command handoff

P0.5 is a pure `FeasibleDecision -> PowerCommand` boundary, separate from this
Simulator demo's `ActuationHandoffResult`. Approved charge/discharge/idle maps
to positive/negative/zero kW; command identity and timing come explicitly from
the caller. It neither calls Runtime nor executes a device command. P0.4 remains
the separate transport-neutral Device Adapter boundary: a current caller
`PowerCommand` enters P0.3 admission/safety/runtime before P0.4 forms a
`DeviceTransmissionRequest` and adapter evidence. P0.6 now provides a one-cycle
caller-driven composition of these existing boundaries. Its audit evidence and
current-caller continuation are separate: evidence cannot restore command or
adapter authority, while continuation contains only the exact P0.3 next runtime.
P0.4 is post-tick audit: ACK/actual facts do not replace P0.3 reconciliation,
and unavailable facts do not claim zero power or physical completion. This is
not a real protocol, network, HIL, or hardware-control demo. The phase order is
P0.3 Controlled Runtime, P0.4 Device Adapter Boundary, P0.5 Command Handoff,
then P0.6 controlled composition.

## Edge P0.6–P0.7 组合周期阅读入口（P0.7 已合并 main）

P0.6 是一次 caller-driven composition：approved `FeasibleDecision + EdgeCommandMetadata` 经 P0.5 生成
`PowerCommand`，进入一次 P0.3 admission/tick，再保留 P0.4 observation/transmission/ACK/actual audit。
P0.7 只让 caller 以 one-shot continuation 显式接续下一个 cycle；caller 不传 `PowerCommand`，也不能由
receipt、ACK、trace 或 previous actual 恢复 command authority。successful cycle 有一次 handoff、一次 tick 和
一次 admitted transmission；任何 failure 或 non-admission 都会终止当前 session，recovery 要新 session。

这是 transport-neutral、同步的教学入口。P0.7 已通过 PR #197 合并到 main，merge SHA 为
`f10852895b289c12d86f7d74fe84d33425411c15`；它仍不是本 Simulator demo 的设备控制功能，也不含真实 transport、
PCS/BMS、HIL 或 hardware。准确 public API 和 focused test 阅读命令见
`docs/learning/RESIDENTIAL_EDGE_P0_6_P0_7_GUIDE.md`。
