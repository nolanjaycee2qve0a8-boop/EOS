# TASK-148 Multi-Opportunity Schedule-Aware Grid Charge Reservation

## 目标

新增并行的 schedule-aware cheap-grid-charge reservation boundary。它消费 TASK-147
已经完成的 `MultiOpportunityHeadroomSchedule`，把当前 SOC 与 schedule 首项的
schedule-adjusted target 转换为当前时段允许的 grid-charge power。它不改变 TASK-133 的
`HeadroomAwareGridChargeReservation*` 语义或实现。

## 公共合同

- `MultiOpportunityGridChargeReservationInput`
- `MultiOpportunityGridChargeReservationResult`
- `MultiOpportunityGridChargeReservationBoundary`
- `DeterministicMultiOpportunityGridChargeReservationCalculator`

Input 持有 exact `headroom_schedule`、`BatteryOptimizationState`、
`BatteryOptimizationModel`、requested power 与 caller-supplied duration。它强制：

```text
headroom_schedule.source_input.battery_model is battery_model
```

数值相等而重建的 model 会被拒绝；不允许 value-only provenance。

## 首项选择与空 schedule

非空 schedule 仅选择 `schedule.entries[0]`，并保持 exact identity：

```text
result.selected_schedule_entry is schedule.entries[0]
```

该 entry 是下一段可见 PV opportunity 的 schedule-adjusted target，已经包含后续机会及其间
natural-depletion potential。这里不会使用其 TASK-132 standalone target、末项 target、最小
target 或 full-horizon blind aggregate。

空 schedule 没有 future PV headroom reservation：`selected_schedule_entry is None`，
`target_soc_fraction = battery_model.max_soc_fraction`。此时请求仍会受到当前 SOC room、
model max-charge power 与 requested power 的约束。

## 精确 reservation 公式

```text
target_soc = first schedule-adjusted target, or max_soc for an empty schedule
soc_room = max(target_soc - current_soc, 0)
stored_energy_room_kwh = soc_room * usable_capacity_kwh
required_input_energy_kwh = stored_energy_room_kwh / charge_efficiency
duration_hours = duration_seconds / 3600
soc_limited_charge_power_kw = required_input_energy_kwh / duration_hours
allowed_grid_charge_power_kw = min(requested, max_charge_power, soc_limited_power)
```

`reservation_applied` 等于 `allowed < requested`。这表示最终 allowance 少于 caller request；
它可能由 schedule SOC room、current SOC 或 model charge-power cap 导致，而不推断唯一原因。

## 证据链与边界

```text
Result
  -> Input
  -> exact MultiOpportunityHeadroomSchedule
  -> exact first schedule entry
  -> exact opportunity / TASK-132 requirement / depletion evidence
```

TASK-148 不导入或检查 raw forecast，不重新运行 opportunity segmentation、TASK-132、TASK-147
calculator，也不计算 depletion。它不产生 `DecisionIntent`，不接入 candidate planning、physical
optimization、MPC、daily runner 或 demo；是否请求 cheap-grid charge 仍由 strategy/candidate
planning 决定。

## TASK-146 / TASK-147 诊断

双机会 fixture 证明：当 later opportunity 在扣除 gap depletion 后仍保留 headroom requirement 时，
schedule-adjusted 首项 target 低于该首项 TASK-132 standalone target；同一 current SOC/request 下，
schedule-aware allowance 因而更小。此为该诊断配置的证据，不是所有 schedule 的硬编码比较不变量。

## 验证

- `pytest`
- `ruff check .`
- `ruff format --check .`
- `mypy .`
- `git diff --check`
