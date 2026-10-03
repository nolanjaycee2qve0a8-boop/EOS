# 缺陷查找 Campaign 验证记录

## 基线与范围

- 不可覆盖基线：`6785e5f2d569e93f0524e19cb0a4d3aa6e2ec334`
- 分支：`example/virtual-home-storage-defect-campaign`
- 只新增 Campaign、测试、中文指南和 README 入口；冻结核心未修改。

## 初始失败证据

1. 第一次执行在创建 fixture 前没有创建场景输出目录，触发
   `ValueError: output_path parent directory must already exist`。没有场景进入核心；
   已修复新增 Campaign 工具并保留该证据。
2. 初始 S04/S06/S08 fixture 使用默认 0.50 CNY/kWh，却预期现有 net-load 策略
   放电。代码审查确认放电合同要求价格达到 0.80 阈值且存在负载缺口；fixture 改为
   显式 0.90，以真正测试物理下界/限幅。原始 idle 结果未冒充物理失败。
3. 初次报告把出口净收益拒绝写成泛化 ledger failure；源码核对发现
   `DailyEconomicLedger` 强制净成本非负，而 extended outcome 允许负值，现分类为
   `NEGATIVE_REALIZED_NET_COST_REJECTED` 跨合同缺陷。

## 当前确定结果

- 场景定义：18；Schedule/Economic/输入合同结果：35。
- `PASS=16`、`LIMITATION=8`、`FAIL=8`、`REJECTED_AS_EXPECTED=3`。
- 唯一 FAIL 类型为两种跨合同问题：负的日净成本被拒绝、负进口价被拒绝。
- LIMITATION 为零出口/弃光能力、纯价格套利范围和两种完全错报预测风险。
- 已完成路径没有功率平衡、SOC 积分、SOC/功率边界或 identity 失败。

## 已完成检查

```bash
/workspace/eos-cloud-prep/venv/bin/ruff check \
  examples/virtual_home_storage_defect_campaign \
  tests/integration/test_virtual_home_storage_defect_campaign.py

/workspace/eos-cloud-prep/venv/bin/ruff format --check \
  examples/virtual_home_storage_defect_campaign \
  tests/integration/test_virtual_home_storage_defect_campaign.py

/workspace/eos-cloud-prep/venv/bin/mypy \
  examples/virtual_home_storage_defect_campaign/campaign.py \
  tests/integration/test_virtual_home_storage_defect_campaign.py

/workspace/eos-cloud-prep/venv/bin/python -m pytest \
  tests/integration/test_virtual_home_storage_defect_campaign.py -q
```

结果：Ruff、格式、Mypy 通过；新增测试 `6 passed in 1.31s`。

## 相关与全量回归

```bash
/workspace/eos-cloud-prep/venv/bin/python -m pytest \
  tests/integration/test_virtual_home_storage_defect_campaign.py \
  tests/integration/test_virtual_home_storage_day.py \
  tests/unit/ems_simulator/test_residential_campaign_b.py \
  tests/unit/ems_simulator/test_residential_campaign_c.py \
  tests/unit/ems_simulator/test_residential_campaign_d.py -q
```

结果：`29 passed in 33.51s`。

仓库级门禁：

```bash
/workspace/eos-cloud-prep/venv/bin/ruff check .
/workspace/eos-cloud-prep/venv/bin/ruff format --check .
/workspace/eos-cloud-prep/venv/bin/mypy .
/workspace/eos-cloud-prep/venv/bin/python -m pytest
```

结果：Ruff 通过；858 个文件格式通过；Mypy 对 505 个源文件无问题；
`3014 passed in 428.61s (0:07:08)`。

异常 SVG 已用 Inkscape 渲染为 760×390 PNG 目视检查，分类、计数、标题和模拟边界
均清楚，无裁切或重叠。

## 独立只读复核与修正

独立 fresh-context 复核先确认场景分类、手算功率/SOC 和冻结核心零差异，并指出
三项 P2 证据缺口：ledger 失败路径未输出独立成本分解、机器矩阵未保存 forecast
曲线、S14 未把 UTC 连续性写成结果与断言。候选随后只修改本 Campaign 与测试：

- ledger 调用前独立计算并输出 export revenue、degradation 和 net cost；S02/S05/
  S07/S09 的净成本分别为 `-0.40/-0.05/-1.25/-2.00 CNY`；缺陷分类还要求
  对应的精确异常类型与文本；
- 矩阵保存 realized/forecast PV、load、tariff 的完整 24 点曲线；
- 结果保存实际 trace 的首末 UTC 时间，S14 同时验证 SOC 延续和相邻一小时边界。

修正后新增测试、相关回归及定向 static 复跑：`6 passed in 1.28s`、
`29 passed in 34.73s`，Ruff、格式、Mypy 均通过。独立审查再次重放上述三项，结论
为 **no findings**；确认 Schedule/Economic 的 S14 均从
`2026-03-01T23:00:00+00:00` 连续到 `2026-03-02T00:00:00+00:00`，冻结核心相对
基线仍为零差异。

仓库级 `3014 passed` 在证据补强前已按本批要求执行一次；补强只涉及 Campaign
证据字段、矩阵和对应断言，随后未重复全量测试，以相关回归与定向 static 覆盖。
