# Residential EMS 1.0 — Validation Campaign A–F Consolidation

## 1. 文档目的与状态

本文是 Residential EMS 1.0 Campaign A–F 的统一验证收口说明。它汇总已合并到
`main` 的验证编排、测试合同和各 Campaign 详细报告，供审计、学习和管理层沟通使用；它
**不替代** `RESIDENTIAL_CAMPAIGN_A.md` 至 `RESIDENTIAL_CAMPAIGN_F.md` 的逐项矩阵、
证据字段和复现说明。

基线为 `ac08a66`（PR #186，Campaign F 已合并且 CI 成功）。Residential EMS 1.0
仍处于 functional freeze。A–F 是冻结控制链的验证与报告层，不新增控制能力，也不构成
production Runtime、硬件、HIL、PCS/BMS/DSP、现场或客户部署认证。

## 2. Functional-freeze 边界

冻结的对象包括 Strategy、MPC、optimizer、physical revision、Feasibility、Actuation、
Simulator、ledger、acceptance、公开 API 和 Runtime。Campaign 编排只提供 caller-owned
事实、调用既有冻结路径、保留 trace/evidence，并检查结果与发布证据；它不会把实验结果
反向写回候选规划或实际执行。

```text
validation facts / orchestration
        ↓ read-only composition
frozen planning → frozen execution → retained evidence
        ↑                         ↓
   no feedback into control   audit / report / publication gate
```

## 3. A–F 验证演进路线

```text
Campaign A  → 冻结基准与基本接受性
Campaign B  → 物理与经济边界
Campaign C  → 单日确定性预测误差
Campaign D  → 多日连续性与账务连续性
Campaign E  → 独立 fixed-seed 合成预测样本
Campaign F  → 跨日相关误差与 deterministic tail robustness
```

这条路线增加的是证据覆盖与可审计性，而非控制复杂度。Campaign E/F 的样本是合成、
固定种子、可复现的描述性验证：它们不是实际天气/负荷概率分布，不给出置信水平，也不
构成生产可靠性认证。

## 4. A–F 统一计数矩阵

| Campaign | 验证目的与时间尺度 | 环境 / 样本 | Schedule/Economic logical paths | 实际 runner / Simulator 执行 | 轨迹复用与 anchor | 不确定性 / 基线 | 接受状态与核心结果 | 明确未覆盖 |
| --- | --- | ---: | ---: | ---: | --- | --- | --- | --- |
| A | 冻结后 24h 确定性基准与接受性 | 24 个 24h 场景 | 48 | 48 个日路径 | 无 accounting reuse；A01/TASK-175 为参考 | 完美 caller-supplied forecast | PASS；冻结路径在显式场景矩阵中通过 hard acceptance | 预测误差、多日、概率、硬件 |
| B | 24h PCS、SOC、tariff 与 accounting 边界 | 72（B1=18、B2=12、B3=18、B4=24） | 144 | 102 个唯一控制执行 | B4 的 24 条逻辑路径复用 3 对既完成轨迹，仅重建 ledger/comparison | 完美 forecast；会计参数敏感性 | PASS；边界与 ranking observation 可见，但非策略优劣判定 | 预测误差、跨日、现场物理额定认证 |
| C | 24h 确定性 forecast-error 行为 | 3 环境 × 13 cases = 39 | 78 | 78 个日路径 | 无 reuse；同环境/策略 perfect case 为 anchor | 明确 PV/load/tariff bias 与时间偏移 | PASS；forecast/realized 分离及 actual-power regret/divergence 可审计 | 概率分布、跨日记忆、现场预测 |
| D | 连续 7/30 天 SOC、时间和账务 | 6 sequences、88 scenario-days | 12 个多日路径 | 176 个 24h 日执行 | 无 reuse；各 Strategy 独立 SOC carry | 每日完美 forecast；D01/D02/D03 等固定序列 | PASS；0 continuity/accounting hard failure，6 comparisons 均 TIED | 多日预测不确定性、全局多日最优、重启恢复 |
| E | 独立 seeded synthetic 单日概率刻画 | 3 环境 × 64 = 192 samples | 384 sampled paths | 384 sampled + 6 perfect anchors = 390 | 6 fresh anchors 仅作 read-only 参照 | fixed seed `20260817`；CRN 配对 | PASS；192 strategy comparisons、384 sample-to-anchor regrets；18 个根输出文件 | 现实概率/置信认证、相关多日误差、生产可靠性 |
| F | 相关误差、跨日连续性和 deterministic tails | 48 core + 12 tail = 60；420 scenario-days | 120 sampled/tail + 6 anchors = 126 多日路径 | 840 sampled/tail + 42 anchor = 882 个日执行 | 6 fresh seven-day anchors；tail 与 core 统计隔离 | fixed seed `20260818`；Cholesky + AR(1)；4 类 unweighted tail | PASS；publication gate 覆盖最终 908 个递归证据文件 | 真实相关分布、置信/可靠性认证、随机优化、HIL/现场 |

### 4.1 计数口径

- **logical path**：一个可报告的 Schedule 或 Economic 路径记录；不等于每次实际运行。
- **actual runner execution**：一次冻结的 24h daily runner/Simulator 执行。D/F 的多日路径由多次
  日执行组成。
- **accounting-only reuse**：B4 复用已完成的控制轨迹，只在显式会计输入下重新构建 ledger/
  comparison；不得把它误报为控制重跑。
- **scenario-day**：D/F 中一个多日序列的一个 24h 输入日；F 为 420，不能与 60 个场景混写。
- **hourly trace**：24h daily execution 的 24 条实际 trace。F 分别有 20,160 sampled/tail 与
  1,008 anchor 小时记录。
- **strategy comparison**：同一场景的 Economic 对 Schedule 比较；E 为 192，F 为 60。
- **regret comparison**：一条路径相对同环境/同 regime/同 Strategy perfect anchor 的比较；E 为
  384，F 为 120。
- **perfect anchor**：独立执行且只读的冻结基准，不进入 sampled/core 的统计群体。

## 5. 验证对象与事实权威层级

```text
caller forecast facts ──→ ForecastHorizon ──→ planning only

caller realized facts ──→ DailySimulationScenarioInput ──→ Simulator actual trace
                                                           ↓
                                      ledger / comparison / acceptance / report
```

实现、测试和最终生成器合同是数值与计数的事实权威；详细 validation 文档说明其语义；
汇总文档只做交叉索引。历史文本曾在 Campaign E/F 发布前将它们写为 `local`；合并历史
`bec48ce`（PR #185）和 `ac08a66`（PR #186）已取代该临时状态，故本文及更新后的记录以
已合并基线为准。

## 6. Forecast 与 realized facts 的边界

Forecast 是 planning 输入：它可由 C 的确定性扰动、E 的独立合成样本或 F 的相关/尾部
变换产生。realized PV、load、tariff 是执行与结算输入；它们进入 Simulator，不能被
forecast 替换。因而“forecast 好/坏”与“实际执行发生什么”是两个需保留来源的事实层。

## 7. Planned 与 actual execution 的边界

计划功率是 MPC 在当前信息下提出的请求；Simulator actual battery power 才是执行事实。
C/E/F 的 actual-power divergence 逐小时读取
`simulation_trace.state.battery_result.actual_power_kw`，不把 planned request 当成实际执行。
这使物理修正、Feasibility、Actuation 与 Simulator 后的差异可被审计，而不会由报告层重算或伪造。

## 8. 单日与多日 SOC continuity

单日 Campaign 将每个 24h 路径作为完整执行单元。D/F 的多日编排不创建新的多日控制器：
每个 Strategy 只把自己上一日 Simulator `next_state.soc` 传给下一日，两个 Strategy 的
SOC carry 严格分离，并保持一小时 timestamp 连续性。预测 SOC 不能替代下一日实际初始 SOC。

## 9. Flow accounting 与 terminal stock accounting

日内 import cost、export revenue 与 degradation 是**flow**，可按日累加；terminal energy value
是 horizon 终点的**stock**，只能按最终实际 SOC 计一次。D/F 的多日聚合遵循：

```text
adjusted net cost
= Σ(import cost - export revenue + degradation)
 - terminal value(final actual SOC)
```

逐日 terminal value 不得相加；否则会把同一终端储能资产重复计价。

## 10. Perfect anchor、regret 与 Strategy comparison

同一术语回答不同问题：

- **Strategy comparison**：在同一 forecast/realized 实验条件下比较 Economic 与 Schedule。
- **perfect anchor**：同环境、同 Strategy 的完美 forecast 基准。
- **regret**：实验路径的 adjusted cost 减去该 anchor 的 adjusted cost；它描述 forecast
  扰动相对基准的变化，不直接证明某 Strategy 有或无价值。
- **TIED**：确定比较语义下成本相等；它不等于“策略无价值”，可能表示 economic gate 正确
  保留已经济支持的 Schedule 行为。

## 11. CRN、Cholesky、AR(1)、core/tail 的含义

CRN（common random numbers）让同一 sampled scenario 的 Schedule 与 Economic 接收完全相同的
caller-owned forecast facts，降低比较中的抽样噪声；两条控制路径仍独立执行。F 的相关矩阵与
Cholesky lower factor 将独立 innovation 转为声明的 PV/load/tariff 联动误差；它是透明的
实验假设，不是现场标定模型。AR(1) 将当天 latent 与前一日 latent 相连，表达跨日误差记忆，
而不宣称现实天气的概率规律。

F 的 core 是固定种子下的描述性统计集合；tail 是单独、无概率权重的 deterministic 压力案例。
两者必须隔离，tail 不进入 core mean、standard deviation、percentile 或 ECDF。

## 12. Acceptance 与 publication evidence contract

hard acceptance 关注 BLOCKER/MAJOR、物理/账务/provenance 等已有接受性证据；策略排名、
成本差异或 revision 高低是人工审查观察，不自动构成 hard failure。F 还采用 fail-closed
publication gate：语义、非最终工件、finalization 和最终工件合同均通过后才输出 PASS。
该门禁控制**证据发布**，不是设备控制；它不改变任何已完成轨迹或下一次决策。

## 13. A–F 主要数值结果

- A：24 场景、48 完整轨迹，hard acceptance PASS；建立 TASK-175/A01 冻结指纹。
- B：72 逻辑场景、144 路径记录、102 唯一控制执行；B4 证明 accounting-only sensitivity 可在
  不重跑控制的条件下审查。
- C：39 场景、78 fresh 执行；将 deterministic forecast error 与 authoritative actual-power
  divergence 连起来。
- D：88 scenario-days、176 日执行、6 条多日比较均 TIED；连续性和 terminal-once accounting
  通过。
- E：192 synthetic samples、390 total actual executions、192 strategy comparisons、384 regrets；
  sampled trace 9,216 行与 anchor trace 144 行分离。
- F：60 scenarios、420 scenario-days、126 independent seven-day paths、882 日执行与 908 个
  递归 evidence files；最终 publication/hard status PASS，core/tail 与 argmax evidence sets
  均可审计。

## 14. 已证明的能力

- 冻结 Residential EMS 1.0 在 A–F 声明的**合成、确定性**验证范围内，能够复用同一控制链完成
  单日、多日、误差、账务、比较和证据发布检查。
- actual Simulator SOC、grid/battery execution trace、ledger 和比较之间的来源链保持可核验。
- Schedule/Economic 能在相同事实下公平比较；经济 gate 的 TIED 行为被保留为有效结果。
- 多日 Strategy-specific SOC carry、flow/terminal 会计边界和 fail-closed evidence gate 已有测试与
  生成器合同覆盖。

## 15. 尚未证明的能力

- 真实天气/负荷/电价预测准确性、概率校准、置信水平或生产可靠性。
- HIL、设备接口、PCS/BMS/DSP 通信、实时调度、故障恢复、现场安全和客户部署。
- 多站点/多设备差异、温度和真实老化机理、真实 tariff/收益结算、长期经济最优性。
- 随机/鲁棒优化或全局多日最优控制。A–F 评估冻结路径，不把这些实验升级为新的优化器。

## 16. 下一阶段建议

不启动 Campaign G 或扩大合成矩阵。建议将后续投入转向产品化验证：先建立真实设备与安全边界，
再校准现实数据与预测模型，并补齐运行可靠性与交付治理。

| 优先级 | 建议投入 | 目的 |
| --- | --- | --- |
| P0 | 真实设备接口、HIL、PCS/BMS 通信与安全边界 | 将仿真执行事实与受控硬件闭环分层对接 |
| P1 | 真实 forecast、tariff、load、PV 数据及概率模型校准 | 用现场证据替代合成分布假设 |
| P1 | 故障、通信中断、时钟漂移、重启恢复、数据缺失 | 建立运行可靠性与安全降级验证 |
| P2 | 多设备差异、温度/衰减、区域与用户分群 | 扩展模型适用域 |
| P2 | 运营监控、版本治理、审计与客户交付证据 | 支撑可运营、可追溯交付 |

这些是从仿真验证走向产品化的下一阶段范围，不是对当前冻结仿真体系的缺陷定性。

## 17. 管理层摘要

**我们验证了什么？** A–F 在冻结 Residential EMS 1.0 上，逐步验证了确定性基准、物理/经济
边界、单日预测误差、多日连续性、独立合成样本及相关/尾部压力下的 trace、账务和证据合同。

**为什么重要？** 它把“算法输出”分解为 planning、actual execution、SOC carry、ledger、comparison
和 publication evidence 六条可审计链，降低由单一图表或单次运行得出结论的风险。

**最可信的结论是什么？** 在明确的合成和固定种子范围内，冻结控制链可重复执行、保持实际
Simulator 事实权威、维持多日 SOC/账务边界，并以 fail-closed 方式发布完整证据。

**不能过度解读什么？** 这些结果不是现实概率、HIL、硬件安全、现场可靠性或客户部署认证；
TIED 也不等同于策略无价值。

**进入真实产品前还缺什么？** 需要 P0 设备/HIL/通信安全边界，随后以 P1 的真实数据校准和
故障运行验证为主，再建设 P2 的机群适配与运营审计能力。

**建议下一阶段投入什么？** 停止扩大合成 Campaign，优先把已有 evidence contract 接到可控 HIL
和真实 telemetry 的产品化验证链上，同时保持 freeze 下的版本可追溯性。
