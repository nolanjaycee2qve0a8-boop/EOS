# 场景矩阵（执行前合同）

所有正常场景为 24×1 小时；未列小时为 0 kW，默认进口价 0.50 CNY/kWh、出口价
0.20 CNY/kWh、10 kWh 电池、SOC 范围 20%–100%、3 kW 充放电上限、95% 效率。

| ID | 目标 | 关键输入 | 预期/独立判定 | 既有覆盖 | 预定分类 |
| --- | --- | --- | --- | --- | --- |
| S01_MIN_SOC_LOAD | 空电供载 | 初始 SOC=20%，h0 load=1 | 不放电；grid import=1；SOC=20% | B 仅扫初始值，未隔离负载 | 物理边界 |
| S02_MAX_SOC_PV | 满电 PV 盈余 | 初始 SOC=100%，h0 PV=2 | 不充电；剩余功率售电；SOC=100% | 未覆盖精确 max | 物理/弃光边界 |
| S03_EXACT_MAX_FILL | 恰好充至上限 | 初始 95%，h0 surplus=0.526315789 kW | SOC 恰为 100%，不得越界 | 未覆盖精确等号 | 阈值 |
| S04_EXACT_MIN_DRAIN | 恰好放至下限 | 初始 25%，h0 deficit=0.475 kW、进口价 0.90 | SOC 恰为 20%，不得越界 | 未覆盖精确等号 | 阈值 |
| S05_PV_STEP_UP | PV 突升 | h12 PV 0→5，load=1，初始 20% | 充电≤3；平衡成立；多余功率售电 | C 只有整曲线缩放/时移 | 突变 |
| S06_LOAD_STEP_UP | 负载突升 | h18 load 0→6、进口价 0.90，初始 100% | 放电≤3；不足由购电补齐 | 高晚峰非单点 | 突变 |
| S07_CHARGE_LIMIT | 充电功率限幅 | h0 PV=10，初始 50% | battery≤+3；剩余售电 | B 扫 PCS，未隔离极端盈余 | 功率限制 |
| S08_DISCHARGE_LIMIT | 放电功率限幅 | h0 load=10、进口价 0.90，初始 100% | battery≥−3；剩余购电 | B 扫 PCS，未隔离极端缺口 | 功率限制 |
| S09_ZERO_EXPORT_FULL | 零出口与满电弃光 | export_limit=0，SOC=100%，h0 PV=10 | 若仍售电则记能力局限；不得伪称弃光 | 零出口合同未组合入日 runner | 限制缺口 |
| S10_NEGATIVE_PRICE | 负进口价 | h0–5 tariff=−0.20，h18–21=0.90，无 PV/load | 负价必须原样保留；若购电则成本为负；仅在现有经济门控内解释 | B 仅非负 TOU | 经济边界 |
| S11_PRICE_SPIKE_IDLE | 纯价格尖峰 | h18 tariff=5.00，无 PV/load，SOC=80% | 若 idle，记录策略不做纯套利；不能称优化缺陷 | 未隔离纯价格信号 | 策略范围 |
| S12_FALSE_PV_FORECAST | 虚假 PV 预测 | h12 forecast PV=5、actual PV=0、load=2 | actual 平衡/SOC 以 realized 为准；若由电网充电则记策略局限 | C 最大 ±25% | 预测误差 |
| S13_MISSED_LOAD_SPIKE | 漏报负载尖峰 | h18 forecast load=0、actual load=6、进口价 0.90、SOC=100% | actual 平衡/SOC 以 realized 为准；若不放电则记策略局限 | C 最大 ±25%/±2h | 预测误差 |
| S14_CROSS_MIDNIGHT | 两日跨午夜状态 | day1 末实际 SOC 传入 day2；连续 UTC 时间 | day2 initial is day1 final；各策略链隔离 | D 大矩阵已有，缺最小复现 | 多日状态 |
| S15_LOW_EFFICIENCY | 低效率与账本 | ηc=ηd=80%，h8 PV=2、h18 load=1 且进口价 0.90 | SOC 用 0.8 独立复算；成本/退化按 actual 积分 | B 不扫效率 | 模型参数 |
| S16_23_POINT_CURVE | 缺失小时 | PV 仅 23 点 | runner 前 ValueError | 单元合同有，端到端报告无 | 输入拒绝 |
| S17_NAN_PV | 非有限输入 | PV 含 NaN | runner 前 ValueError | 单元合同有，端到端报告无 | 输入拒绝 |
| S18_HALF_HOUR_STEP | 非一小时步长 | 一个 duration=1800 s | runner 前 ValueError | 日合同固定 1h | 输入/时间步拒绝 |

购电功率上限不是当前 24 小时输入合同的一部分，因此不伪造一个“进口限幅”场景；
报告将其列为产品/测试能力缺口。满电且无法出口时也没有 PV curtailment 输入/输出，
S09 用实际行为确认这一边界，而不新增隐式弃光算法。
