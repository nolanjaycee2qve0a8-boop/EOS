# TASK-176 — Residential EMS Validation / Acceptance Suite

## 目标

TASK-176 是 Residential EMS 1.0 的确定性功能冻结门。它定义验收 KPI、PASS/FAIL、严重度、失败证据、simulation-campaign readiness 与未来 campaign 可复用的报告语言；它不新增控制、优化、物理或硬件能力。

```text
completed control / Simulator trajectory
        + TASK-173 DailyEconomicLedger
        + TASK-174 EconomicComparisonExplanation
                         |
                         v
          DeterministicResidentialAcceptanceEvaluator
                         |
                         v
findings + KPIs + READY_FOR_SIMULATION_CAMPAIGN
```

## 分类、严重度与状态

分类：`physical_safety`、`control_semantics`、`accounting_reconciliation`、`economic_behavior`、`explainability`、`quality_metric`。

- `BLOCKER`：不安全、物理无效、对账不一致或架构/反馈旁路。
- `MAJOR`：冻结的参考行为或必须 provenance/explanation 缺失。
- `MINOR`：非关键报告问题。
- `INFORMATIONAL`：质量观察；不阻塞 readiness。

finding 的状态仅为 `pass`、`fail` 或 `not_applicable`。质量变差不能被模糊地表示为 PASS；相反，诸如 import/export/throughput/self-consumption 等质量 KPI 默认只是诊断量，除非某个场景明确冻结它。

总体就绪规则：只有零 `BLOCKER` FAIL 且零 `MAJOR` FAIL 才是 `READY_FOR_SIMULATION_CAMPAIGN`。这绝不表示 ready for hardware、PCS、field deployment 或 customer use。

## 冻结场景

- A1：TASK-175 Residential Reference Demo，导出允许；冻结能量、成本和 `Schedule/Economic = TIED` 指纹。
- A2：TASK-161 E1/TASK-172 的 Negative Economic Shift；冻结不经济 cheap-grid charge 的抑制及基准会计下 Economic 更低成本。
- A3：TASK-165/TASK-172 Terminal SOC Divergence；冻结 terminal contribution 的抵消方向与 comparison reconciliation。
- A4–A10：从 TASK-175 完成的实际轨迹读取 PV surplus charge、evening deficit discharge、minimum/maximum SOC、charge/discharge power limit 和 idle/no-action 的参考证据。

TASK-175 在本套件中保持 export allowed；不与 Zero Export 语义混用。Simulator 符号固定为：`grid > 0` 为 import、`grid < 0` 为 export；`battery > 0` 为 charging、`battery < 0` 为 discharging。所有物理对账使用集中 `NUMERIC_TOLERANCE = 1e-12`，不以松散容差掩盖真实偏差。

## 硬性不变量与 KPI

每条适用实际轨迹验收 SOC/power bounds、有限数值、`PV + Grid - Battery = Load`、实际上一 Simulator SOC/Grid feedback、TASK-173 interval/daily reconciliation、TASK-168 outcome 和 TASK-174 four-component decomposition。缺失 provenance、material-action explanation 或固定控制保证分别给出 MAJOR/BLOCKER finding。

`ResidentialAcceptanceKPI` 保持可用于后续 campaign 的统一字段：能源、控制计数、成本/收入/退化/终端价值、四类安全违规、解释缺口和 feedback/reconciliation/provenance/fixed-control 标志。它不引入含义不清的自消费 KPI。

## CLI 与输出

```powershell
python -m ems_simulator.residential_acceptance `
  --output-dir simulation_output_task176_residential_acceptance
```

生成但不提交：

- `residential_acceptance_summary.csv`
- `residential_acceptance_findings.csv`
- `residential_acceptance_kpis.csv`
- `residential_acceptance_report.txt`

报告明确区分软件正确性、物理安全、会计对账与质量观察，并陈述：通过此门仅表示可进入 planned large-scale Simulation Validation Campaign。

## Functional Freeze 与下一阶段

TASK-176 merge 后 Residential EMS 1.0 进入 functional freeze。simulation campaign review 前仅允许 bug fix、validation failure、acceptance/campaign tooling 与报告改动；不新增住宅控制能力，除非获得显式批准。

下一阶段 campaign 应复用本任务的 KPI/finding schema，逐步覆盖 deterministic baseline matrix、physical boundaries、tariff/degradation/terminal-value sensitivity、PV/load/initial-SOC diversity、forecast error、Monte Carlo 与 counterexample mining。本任务不实现这些大规模实验。

当前限制仍包括 perfect/deterministic forecast、无真实天气/forecast-error、无真实 PCS/BMS、无通信失败验证、退化仅为会计证据、无 tariff certification、无工业场站和无多储能验证。
