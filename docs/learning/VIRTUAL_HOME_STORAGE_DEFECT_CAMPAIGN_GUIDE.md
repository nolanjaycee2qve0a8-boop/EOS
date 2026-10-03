# EOS 虚拟家庭储能缺陷查找 Campaign 指南

这个 Campaign 在已验证的 24 小时示例上增加 18 个确定性场景，用独立功率、SOC、
能量和成本复算寻找软件合同不一致与策略能力边界。它只运行模拟，不修改冻结核心，
也不代表实物、HIL、PCS/BMS 或现场控制验证。

本页第 1、2 项保留 Campaign 提交 `bedd238245709bbc91c8372580e0f8bdc9bb42c4`
发现缺陷时的原始解释。后续有符号账本修复已让这两类场景通过；当前合同和修复证据见
[`SIGNED_ECONOMIC_LEDGER_CONTRACT.md`](SIGNED_ECONOMIC_LEDGER_CONTRACT.md)。重新运行
Campaign 时，它们应显示为 PASS，原始修复前输出仍作为历史证据保留。

## 运行

```bash
/workspace/eos-cloud-prep/venv/bin/python \
  -m examples.virtual_home_storage_defect_campaign.campaign \
  --output-dir /tmp/eos-defect-campaign
```

主要输出：

- `simulated_scenario_matrix.csv/json`：执行前场景合同，含目标、显式输入、预期、
  既有覆盖和判定规则；
- `simulated_defect_campaign_results.csv/json`：35 条 Schedule/Economic/输入合同结果；
- `simulated_defect_findings.csv/json`：只保留 FAIL 与 LIMITATION；
- `simulated_defect_report_zh.md`：中文发现、能力边界和修复顺序；
- `simulated_defect_findings.svg`：只显示 PASS、FAIL、LIMITATION 和输入拒绝数量。

静态场景合同见
[`SCENARIO_MATRIX.md`](../../examples/virtual_home_storage_defect_campaign/SCENARIO_MATRIX.md)。

## 为什么没有重复 Campaign B/C/D

- Campaign B 已有 72 格 PCS 功率、初始 SOC、常规 TOU 与会计敏感性扫描；本轮只做
  精确上下界和极端瞬时事件。
- Campaign C 已有 39 个 perfect、±25% 与 ±2h 预测误差；本轮只增加完全虚假 PV
  和完全漏报负载尖峰。
- Campaign D 已运行 7/30 天共 176 条日路径；本轮只保留一个两日跨午夜最小复现，
  核对 day2 initial SOC 是 day1 actual final SOC。

## 六类实际发现

### 1. 出口净收益与 ledger 合同不一致

满电 PV、PV 突升和极端充电限幅可以产生允许的售电。独立会计得到负的
`total_realized_net_cost`（收入高于进口与退化费用），但 `DailyEconomicLedger`
要求该字段非负并拒绝完成轨迹：

```text
ValueError: total_realized_net_cost must be finite and non-negative
```

这与 `ExtendedEconomicOutcomeEvidence` 明确允许负的 adjusted cost 的语义不一致。
它是跨合同缺陷，不是电池或 Grid 算术错误。

### 2. 负进口价合同不闭合

`DailySimulationScenarioInput` 和 Tariff simulator 明确接受有限 signed tariff。
S10 在 −0.20 CNY/kWh 时实际购电约 5.263158 kWh，独立进口成本为
−1.052632 CNY，但 ledger 拒绝负进口价：

```text
ValueError: import_tariff_per_kwh must be finite and non-negative
```

应先决定产品合同：收窄上游输入，或让成本与 ledger 全链支持 signed tariff。

### 3. 零出口和弃光没有进入该日链

S09 设置 `export_limit=0`、SOC=100%、PV=10 kW，结果仍售电 10 kW。当前日 runner
没有零出口功率修正，也没有 PV curtailment/弃光模型。因此不能把结果描述成满足
零出口，更不能伪造一个“弃光 actual”。

### 4. 纯价格尖峰不触发对网套利

无 PV、无负载、SOC=80%、进口价瞬时升至 5.00 CNY/kWh 时，Schedule 与 Economic
都保持 idle。现有 net-load 策略只在有负载缺口时请求放电，不执行纯价格对网放电。
这是策略范围，不自动等于缺陷。

### 5. 虚假 PV 预测会形成额外购电充电

S12 在 h12 预测 PV=5 kW，实际 PV=0、负载=2 kW。策略仍执行 +3 kW 充电，Grid
实际购电 5 kW。Simulator 忠实执行了预测形成的动作；当前动作链没有用 realized
净负载否决该动作。这是需要产品决定的 realized-current guard 缺口。

### 6. 漏报负载尖峰时不放电

S13 在 h18 实际负载=6 kW、进口价=0.90 CNY/kWh，但 forecast load=0。策略保持
idle，6 kW 全部由电网供给，尽管 SOC=100%。这同样说明动作依赖 forecast 当前点。

## 通过的物理与输入边界

- 95% 效率下，0.526315789 kW 充电恰好把 SOC 从 95% 推到 100%；
- 0.475 kW 放电恰好把 SOC 从 25% 降到 20%；
- 极端 PV/负载下实际充放电均限于 ±3 kW，Grid 承担剩余平衡；
- 80% 充放效率场景最终 SOC 的独立结果为 53.5%；
- 两日 Schedule 与 Economic 链都把 day1 69% actual SOC 原样传给 day2；
- 23 点曲线、NaN PV 和 1800 秒步长均在 runner 前 fail closed。

所有已完成 trace 的 `PV + grid - battery = load`、SOC 效率积分、功率/SOC 边界、
decision/provenance/feasible/handoff/Simulator identity 都通过。本轮没有发现
Simulator 电池或 Grid 算术违例。

## 修复后的下一步建议

1. 保留负日净成本和有限负进口价的最小回归与独立复算；
2. 单独设计零出口修正与 PV curtailment 的最小合同；
3. 再分别决定 realized-current guard、纯价格套利和 grid import
   limit 是否属于下一产品范围。

有符号账本修复没有实现这些剩余能力；Campaign 继续只提供模拟复现与证据。
