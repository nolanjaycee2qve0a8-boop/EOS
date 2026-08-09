# TASK-089 — EOS EMS Simulator 1.0 Demo

## 目标

提供第一个可一条命令运行的完整家庭光储 Demo，复用 TASK-082～088 的现有能力并生成工程
可读输出。

## 实现

- `create_demo_scenario()` 构造固定 24-hour PV、Load、Tariff profiles、Battery parameters
  与 initial SOC。
- `run_demo(output_directory)` 依次调用 `DailySimulationRunner` 和
  `SimulationResultExporter`。
- `python -m ems_simulator.demo --output-dir ...` 提供 CLI entry point。
- frozen/slotted `DemoExecutionResult` 保存 exact source input、simulation result、export
  artifact 与 output paths。

## 输出

- `simulation_result.csv`；
- `power_curve.svg`；
- `soc_curve.svg`；
- `daily_summary.txt`。

## 策略说明

Demo 使用 TASK-087 的 simple rule：PV surplus 请求充电；PV insufficient 且 SOC 可用时请求
放电。Battery model 决定实际可实现功率并保护 SOC。该规则只验证 simulator，不是最终 EMS
strategy。

## Architecture

```text
explicit household scenario
        |
        v
DailySimulationRunner
        |
        v
DailySimulationResult
        |
        v
SimulationResultExporter
        |
        +--> CSV
        +--> Power SVG
        +--> SOC SVG
        `--> Daily summary
```

## Non-goals

- 不实现 MPC、Optimization、AI 或 Forecast。
- 不引入 Runtime、Scheduler、Clock ownership、Device、Command 或 Cloud。
- 不修改 Phase 5～8 contracts。
- 不把 Demo rule 声明为生产 EMS 策略。

## Validation

- Demo scenario facts；
- 24-step completion 与 exact provenance；
- 四个 output files；
- CLI one-command execution；
- deterministic repeated output；
- full pytest、Ruff、mypy 与 pre-commit。
