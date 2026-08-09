# TASK-087 — 24h Simulation Runner

## 目标

在不修改 Phase 5、Phase 6、Phase 7 contracts 的前提下，实现 EOS EMS
Simulator 1.0 的第一个完整 24 小时确定性执行入口。

## 输入与输出

- 输入：exact `DailySimulationScenarioInput`。
- 输出：immutable `DailySimulationResult`。
- 输入中 24 个 `SimulationStepIdentity` 按 caller order 使用，每个 step 通过
  `SingleStepSimulationExecutor` exactly once。

`DailySimulationResult` 保存 exact source input、生成的 `SimulationScenario`、24
个 exact `SimulationExecutionTrace` references，以及 23 个显式
`SimulationStepProgression` references。

## 执行流程

```text
DailySimulationScenarioInput
        |
        v
PV / Load profile facts
        |
        v
rule-based Battery request
        |
        v
SimpleBatteryPhysicsModel
        |
        v
GridEnergyBalanceSimulationModel
        |
        v
SingleStepSimulationExecutor
        |
        v
SimulationExecutionTrace x 24
        |
        v
DailySimulationResult
```

PV surplus 产生正的 charging request；PV deficit 且 source SOC 高于 reserve SOC
时产生负的 discharging request；否则产生零 request。Battery physics 仍负责 power、
efficiency 和 SOC boundaries，Grid 使用 realized Battery power，并遵守：

```text
Grid = Load + Battery - PV
```

## Identity 与 progression

- `result.source_input is original_input`。
- 每个 step 使用 exact caller-supplied step identity。
- 每个 trace 保存 exact step、binding、state 和 step result。
- step N 的 Battery next state 是 step N+1 的 exact source state。
- progression 保存 exact previous trace/result 与 exact next input。
- runner 不 copy、deepcopy、serialize 或 reconstruct 已有 evidence。

## Phase 7 executor 复用

Grid balance 需要同一步已完成的 PV、Load 和 Battery results。Runner 先显式协调这些
component results，再以 frozen exact-result adapters 绑定 Phase 7 executor；adapters
只返回其 exact result，不重算物理结果。Grid binding 仍执行 TASK-086 concrete model。
因此 executor contract、binding completeness contract 和 trace contract 均保持不变。

## Non-goals

- 不实现 MPC、Optimization、Forecast 或 AI。
- 不拥有 Runtime、Scheduler、Clock 或自动 loop。
- 不引入 Device、Command、Dispatcher、PCS、BMS 或通信协议。
- 不修改 Phase 5、Phase 6、Phase 7 contracts。
- 不实现 CSV export、plotting 或 daily summary；这些属于后续应用任务。

## Validation

- 24-step exactly-once execution 与 caller order。
- SOC continuity 与 exact progression identity。
- PV/Load/Battery/Grid integration。
- trace completeness。
- deterministic repeatability。
- full `pytest`、Ruff、mypy 与 pre-commit。
