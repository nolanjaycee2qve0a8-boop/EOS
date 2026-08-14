# TASK-147 Multi-Opportunity Headroom Schedule Contract

## 目标

建立纯规划证据合同，以表达一个 forecast horizon 内多段、彼此分离的
PV-surplus opportunity 所需的 battery headroom schedule。它不产生决策、不做
cheap-grid reservation，也不接入 MPC、Simulator 或任何执行路径。

TASK-146 的有限非重复诊断表明两个极端都不充分：full-horizon 直接汇总会过度保守；
first-opportunity-only rolling 虽较少保守，却可能允许夜间 grid charge 占用随后第二段
PV opportunity 需要的空间。TASK-147 因此把单一 target 提升为按 opportunity 排序的
schedule evidence。

## 新增公共合同

- `PVOpportunitySequenceInput`
- `PVOpportunitySequenceEntry`
- `PVOpportunitySequence`
- `PVOpportunitySequenceBoundary`
- `DeterministicPVOpportunitySequenceCalculator`
- `MultiOpportunityHeadroomScheduleInput`
- `MultiOpportunityHeadroomScheduleEntry`
- `MultiOpportunityHeadroomSchedule`
- `MultiOpportunityHeadroomScheduleBoundary`
- `DeterministicMultiOpportunityHeadroomScheduleCalculator`

`MultiOpportunityHeadroomScheduleInput` 显式保留 `control_step_duration_seconds`；
TASK-132 的输入能量公式以该 caller-supplied duration 将功率转换为能量，不能从时间戳
隐式推断，也不读取 clock。输入不包含 current SOC、价格、策略、决策或 grid-charge request。

## Opportunity 分段

`PVOpportunitySequence` 只回答“可见的 PV-surplus opportunities 分别是什么”。active 语义
与 TASK-140 完全相同：`max(PV - Load, 0) > 0`。在一个 active 段中，只有后续确有
surplus 恢复时，长度不超过 `max_inactive_gap_points` 的 inactive gap 才会被保留；超过
tolerance 的 gap 使两段机会保持分离；未被恢复确认的 trailing gap 会被丢弃。

每个 sequence entry 保留 source-index interval、exact `ForecastPoint` references、caller
order、selected `ForecastHorizon` 与开始/结束 timestamp。Sequence 不计算 headroom。

## Headroom、gap 与倒推

每一个 sequence entry 的 selected horizon 都以其 exact object identity 注入 TASK-132 的
`PVHeadroomRequirementInput`。TASK-132 的 PV surplus、charge power cap、charge efficiency
及 usable-SOC-window 公式未被复制或修改。

相邻机会之间的 gap 额外记录两个明确能量域：

- `gap_net_deficit_load_energy_kwh = Σ max(Load - PV, 0) × duration_hours`：负荷侧能量；
- `battery_stored_energy_depletion_potential_kwh = gap_net_deficit_load_energy_kwh / discharge_efficiency`：若该 deficit 由电池供给，电池储能可能减少的能量。

第二项是 future headroom recreation potential，不是已执行的 battery discharge，也不代表
所有 deficit 必由电池承担。

从最后一个 opportunity 向前，schedule 使用下列 deterministic recurrence：

```text
R_last = own_required_headroom_last
R_i = min(usable_battery_energy_range,
          own_required_headroom_i + max(R_(i+1) - depletion_potential_i, 0))
```

随后每个 target 为：

```text
recommended_pre_opportunity_max_soc
= clamp(max_soc - R_i / usable_capacity, min_soc, max_soc)
```

因此 entry 同时保留 TASK-132 原始 standalone target 与本 task 的
schedule-adjusted target；前者从不被覆盖或重解释。

## 行为与 provenance

- 无 opportunity：empty sequence 与 empty schedule；
- 一个 opportunity：schedule-adjusted requirement/target 与 TASK-132 standalone evidence
  完全相同；
- 多个 opportunity：间隔的自然 deficit potential 可降低早期必须预留的后续 headroom，
  但不会低于当前 opportunity 自身 requirement；
- 所有 source horizon、configuration、model、selected horizon、ForecastPoint、TASK-132
  requirement 及 opportunity entry 均保持 exact provenance identity。

TASK-146 型 profile 的测试验证：first-only 的 requirement 小于 schedule 首项，后者又小于
没有考虑 gap depletion 的盲目 full sum（在未触及 usable-range cap 的配置下）。

## 非目标

本 task 不修改 TASK-132、TASK-140、reservation、candidate planner、physical optimizer、MPC
cycle、daily runner 或 demo；不引入价格、经济性、策略、DecisionIntent、OptimizationSolution、
Simulator、Runtime、Device 或 Command 依赖。

## 验证

- `pytest`
- `ruff check .`
- `ruff format --check .`
- `mypy .`
- `git diff --check`
