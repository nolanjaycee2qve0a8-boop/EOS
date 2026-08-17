# TASK-174 — Economic Comparison Explainability

## 目标

TASK-174 对两条已经完成的 TASK-168 `ExtendedEconomicOutcomeEvidence` 做确定性解释：
在明确的会计口径下，哪条路径的 adjusted net economic cost 更低、相差多少、以及由哪些
已完成经济组件造成。它是 evaluation / explainability read model，不是控制选择器。

```text
completed reference TASK-168 outcome
completed candidate TASK-168 outcome
              |
              v
 EconomicComparisonInput
              |
              v
 DeterministicEconomicComparisonExplainer
              |
              v
 EconomicComparisonExplanation
```

## 比较与分解

比较方向固定为 candidate minus reference：

```text
delta_adjusted_cost =
    candidate_adjusted_net_economic_cost
    - reference_adjusted_net_economic_cost
```

- `delta < 0`：candidate 在该会计口径下更优。
- `delta > 0`：reference 更优。
- `delta == 0`：并列。

组件 delta 也固定为 candidate minus reference；面向 adjusted-cost 的签名贡献为：

```text
import_cost_contribution = delta_import_cost
export_revenue_contribution = -delta_export_revenue
degradation_cost_contribution = delta_degradation_cost
terminal_value_contribution = -delta_terminal_value
```

其和必须与 `delta_adjusted_cost` 对账。沿用现有经济测试风格，浮点对账和近零显示使用
绝对容差 `1e-12`；这仅消除算术残差，不改变来源 evidence 或排名语义。负 contribution
表示帮助 candidate 降低 adjusted cost，正 contribution 表示对 candidate 不利。

## 排名、主导因素与身份

`EconomicComparisonRanking` 提供 `CANDIDATE_BETTER`、`REFERENCE_BETTER` 与 `TIED`。
`EconomicComparisonComponent` 记录 import cost、export revenue、degradation cost、terminal
value 与 none。主导因素是绝对值最大的 cost contribution；若有 exact tie，则
`dominant_components` 按固定顺序保留全部并列项，`dominant_component` 为 `NONE`，不会隐藏
并列事实。

结果保持 exact provenance：

```text
result.source_input is original_input
result.reference_outcome is input.reference_outcome
result.candidate_outcome is input.candidate_outcome
```

## 职责边界

TASK-174 不调用 TASK-169/170/171/162/168 calculators，不计算 import cost、export revenue、
degradation 或 terminal value，也不访问 raw ledger intervals。它不运行或改变 Strategy、MPC、
candidate planning、physical optimization、Feasibility、Actuation、Simulator 或 tariff。

TASK-172 回答“在给定敏感度下哪条路径更好”；TASK-173 回答“一条路径的每日经济结果来自
哪里”；TASK-174 回答“为什么两条路径会有差异”。

## 输出

`comparison_summary_csv()` 和 `comparison_explanations_text()` 只序列化已经生成的 explanation。
`write_economic_comparison_outputs()` 写入：

- `economic_comparison_summary.csv`
- `economic_comparison_explanations.txt`

参考 CLI：

```powershell
python -m ems_simulator.economic_comparison_explanation `
  --output-dir simulation_output_task174_economic_explanation
```

CLI 仅作为 TASK-172 基线样例的外层 materializer；核心 comparison boundary 仍只消费已经
完成的 final outcomes。输出目录不纳入版本控制。
