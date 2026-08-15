# TASK-165 Terminal-SOC-Divergence Economic Observation

## 目标

TASK-164 中 E0/E1/E2 的两个实际路径在 horizon 终点 SOC 相同，终端能量价值不能区分路径。TASK-165
使用独立、有限的 24 小时诊断场景，让既有 Schedule-aware 与 Economic Schedule-aware 控制自然形成实际
terminal SOC difference，再只读地应用 TASK-162 与 TASK-163 accounting evidence。

## 场景

初始 SOC 为 `0.50`。00:00--05:00 tariff 为 `0.80`，后续为 `0.85`；`0.85 * 0.95 * 0.95 - 0.80`
为负，因此 existing Economic path 抑制早期 cheap-grid charge。Schedule path 仍通过既有 reservation/
physical chain 充电。原有白天 PV profile 被 cap 到 `0.60 kW`，始终不超过负载，故没有 PV surplus 可在
后段把路径重新拉齐，也没有高价 discharge trigger；这不是直接 SOC 操作。

## 实际结果

首次 actual SOC divergence 出现在 cycle 0（`2026-02-01T00:00:00+00:00`）：Schedule `0.785`，Economic
`0.500`。最终 Schedule/Economic SOC 为 `1.0 / 0.5`。

| Metric | Schedule | Economic | Economic - Schedule |
|---|---:|---:|---:|
| realized import cost | 22.840526 | 18.630000 | -4.210526 |
| terminal energy value | 6.460000 | 2.422500 | -4.037500 |
| net economic cost | 16.380526 | 16.207500 | -0.173026 |

共同 terminal valuation price 为既有 scenario tariff 的最高值 `0.85`。经济路径的较低 realized import
cost 因较低 terminal stored-energy value 而被显著缩小，但没有被抵消或反转。这表明 terminal-state value
在该 fixture 中对路径解释是 decision-relevant；不过该指标仍是 limited accounting（import cost 减 assigned
terminal energy value），不是完整 profit。

## 输出与边界

CLI 输出 comparison CSV、hourly trajectory CSV、summary 和三张 SVG。模块复用 frozen TASK-161 runners，
只读取其 exact completed traces/economic evidence；不改变 TASK-155--163 公式、不引入 terminal target、
新 optimizer、export revenue、degradation、Runtime 或 control integration。
