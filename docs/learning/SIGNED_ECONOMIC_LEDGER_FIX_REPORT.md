# 有符号电价与经济账本修复报告

## 修复前证据

基线为缺陷 Campaign 提交 `bedd238245709bbc91c8372580e0f8bdc9bb42c4`。修复前的
18 场景/35 结果为 `PASS=16`、`LIMITATION=8`、`FAIL=8`、
`REJECTED_AS_EXPECTED=3`。8 条 FAIL 来自 Schedule/Economic 两条路径上的两类合同
断点：

- S02/S05/S07 的合法出口净收益形成负日净成本，ledger 以
  `total_realized_net_cost must be finite and non-negative` 拒绝；
- S10 的有限负进口价已被 Daily input 和 Tariff simulator 接受，import-cost evidence
  却以 `import_tariff_per_kwh must be finite and non-negative` 拒绝。

先写的新回归在未修改实现时得到 `5 failed, 35 passed`，失败点分别落在 import-cost
输入、extended outcome、Campaign 计数、负价 ledger 和连续两日负价 ledger。

## 最小实现

- `ImportCostInput/Evidence`：进口能量继续有限非负；进口电价与其乘积改为有限有符号。
- `EconomicOutcome` 与 `ExtendedEconomicOutcome`：已实现进口成本改为有限有符号；出口
  收入、退化成本、终端价值仍有限非负，identity 与公式对账不变。
- `EconomicLedgerInterval/DailyEconomicLedger`：进口 tariff、进口成本、interval/daily
  净成本及 adjusted net cost 允许有限负值；物理量与其他会计分量的非负约束不变。
- Campaign 仍用独立公式复算全部分量，只把已修复的两类结果从 FAIL 变为 PASS；原有
  零上网、套利和预测局限继续显示为 LIMITATION。

没有裁零、取绝对值或吞掉异常。NaN、正负无穷、负能量、负出口收入、负退化费及
非数值输入仍 fail closed。

## 可复现结果

修复后 Campaign 输出在 `/tmp/eos-signed-ledger-candidate`，结果为：

- `PASS=24`、`LIMITATION=8`、`FAIL=0`、`REJECTED_AS_EXPECTED=3`；
- S02：独立/ledger 日净成本均为 `-0.40 CNY`；
- S05：均为约 `-0.05 CNY`；
- S07：均为 `-1.25 CNY`；
- S10：独立进口成本 `-1.052631578947 CNY`，独立/ledger 日净成本约
  `-0.789473684211 CNY`；
- S09 现在可以完成 `-2.00 CNY` 账本，但仍因 `export_limit=0` 时出口 10 kW 而保持
  `ZERO_EXPORT_NOT_ENFORCED_NO_CURTAILMENT`，没有被包装为 PASS。

正价历史参考账本分别从基线 worktree 和修复工作区生成。三个输出逐字节相同：

- interval CSV：`b70bbce31a37c172ae60b9f2bb4350a6d20a59dd40629831e1597fa853087bf9`
- daily CSV：`30024cb6d082a1ff9b83cb2979195ff26e668673d1bab095044026301f5504c4`
- summary：`c70c44727f973551d68ac9e1cf083b7e35641c87e3d72f3d432eed99c3416f64`

验证结果：相关 optimization/ledger/Campaign/day 测试 `543 passed`；仓库级 Ruff、
859 文件格式检查和 Mypy 505 个源文件通过；唯一一次完整回归为
`3021 passed in 422.30s (0:07:02)`。

Fresh-context GPT-5.6 Sol 只读复核结论为 **no findings**。审查者独立重放 Campaign、
手算 S10、执行 12 个非法输入探针，并验证连续两日负价进口成本分别为约
`-1.252631578947/-0.20 CNY`、实际 SOC 延续且时间戳连续；定向测试 `70 passed`，
focused Ruff、format、Mypy 和 `git diff --check` 均通过。审查未编辑文件，也未重复
全量测试。

## 剩余限制与下一批最小设计

本批没有改变策略与功率执行。仓库已有的 `ZeroExportBoundary` 只保存 exact decision、
provenance 与 Boolean feasibility，并明确禁止修正功率；下一批不应把 correction 偷塞进
这个冻结事实合同。建议让日 runner 先实际调用该边界，再增加一个隔离、确定性的
zero-export correction/curtailment 合同：输入为该 exact feasibility、realized PV/load、
SOC/PCS 限值、显式 export limit 与“是否允许 PV curtailment”；输出分别给出获准电池
功率、受限原因、剩余 grid power 和显式 curtailed PV。`export_limit=0` 且电池无法吸收
全部盈余时，只有在明确允许 curtailment 的场景才能把剩余 PV 记为弃光；否则应 fail
closed 或保留未满足的限制事实，不能伪造设备执行。该设计需下一次单独批准后再实现。

这里的结果仍是固定仿真会计证据，不是实际电价结算、设备控制、PCS/BMS、HIL 或现场
保护证明。
