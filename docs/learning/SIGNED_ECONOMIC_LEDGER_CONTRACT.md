# 有符号电价与经济账本修复合同

本修复以缺陷 Campaign 提交
`bedd238245709bbc91c8372580e0f8bdc9bb42c4` 为不可覆盖的修复前证据。原始 Campaign
结果继续证明两个端到端合同断点：合法出口净收益不能形成负的日净成本，以及上游接受的
有限负进口价不能进入账本。本批修复这两个断点，不覆盖或改写修复前输出。

## 数值语义

- `realized_import_energy_kwh`、进出口能量、负载/PV 能量和电池吞吐量仍必须有限且
  非负；功率符号与能量分类规则不变。
- `import_tariff_per_kwh` 允许任意有限实数。负值表示该时段进口电能的单位结算价格
  为负，不裁零、不取绝对值。
- `realized_import_cost = realized_import_energy_kwh * import_tariff_per_kwh`，因此它是
  有符号现金流分量，必须有限，但可以为负。
- `realized_export_revenue`、`battery_degradation_cost`、终端能量价值及其单位假设仍为
  有限非负量；本批不增加负出口价、负退化费或新币种模型。
- interval/daily realized net cost 与 terminal-adjusted cost 是有符号净额。出口收入超过
  进口成本与退化成本时，日净成本可以为负；所有分量仍必须逐项对账。

## 影响范围

最小实现范围为 import-cost evidence、消费该 evidence 的 economic outcome、extended
outcome 和 completed-trajectory ledger，以及直接测试和教学 Campaign。既有正价参考样本
的数值与输出必须不变；NaN、无穷、负能量及非数值输入继续 fail closed。

本批不修改策略、预测、功率可行性、Simulator 物理积分、零上网、PV 弃光、纯价格套利
或 realized-current guard，也不接入设备、协议、HIL 或真实结算系统。金额字段只代表当前
单币种仿真会计证据，不代表已完成现金结算。
