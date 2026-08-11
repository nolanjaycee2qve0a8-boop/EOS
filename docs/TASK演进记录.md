# EOS TASK 演进记录

## 1. 记录说明

本文记录 EOS 从 TASK-001 开始的工程演进。每个 TASK 均按目标、实现、架构意义、
新增文件、验证结果和关键设计决策记录。

“验证通过”表示对应 TASK 在当时完成了要求的 pytest、Ruff、mypy 等质量门；历史
精确用例数以对应 PR 和 CI 记录为准。TASK-034～036 的当前基线测试数在条目中明确
记录。

后续每完成一个 TASK，必须在本文末尾追加新条目，并同步更新学习手册与架构说明。

## TASK-001

**目标：** 初始化 EOS Reference Implementation 仓库和工程基础。

**实现内容：** 建立 architecture、kernel、capability、simulator、tests、examples、
handbook 和 tools 目录，并配置 Python 3.12、pytest、Ruff、mypy、pre-commit。

**架构意义：** 先固定工程边界和质量门，再进入领域实现，体现 architecture drives
implementation。

**新增文件：** `pyproject.toml`、`README.md`、`LICENSE`、`CHANGELOG.md`、
`CONTRIBUTING.md`、Ruff/mypy/pre-commit 配置及 package markers。

**验证结果：** 初始化质量检查通过；仓库结构与规范一致。

**关键设计决策：** 不引入 EMS 算法，不创建通用 utils/misc/helper 目录，不建立
重复 Python package。

## TASK-002

**目标：** 建立不可变的基础领域对象。

**实现内容：** 引入 Snapshot、Mission、Command、Event 以及强类型 ID。

**架构意义：** 为决策、事件、命令和重放提供稳定且可验证的领域语言。

**新增文件：** `kernel/domain/*`、`kernel/ids/*` 及对应 unit tests、ADR。

**验证结果：** immutable、validation、public imports 和完整回归检查通过。

**关键设计决策：** 领域对象 frozen/slotted；时间、ID 和字段验证显式；runtime 才能
拥有状态转换。

## TASK-003

**目标：** 建立确定性决策流水线。

**实现内容：** 定义 `DecisionPolicy`、`DecisionResult` 和 `DecisionPipeline`。

**架构意义：** 把领域输入与决策输出放入纯、可替换、可测试的合同。

**新增文件：** `kernel/decision/policy.py`、`result.py`、`pipeline.py` 及测试、ADR。

**验证结果：** 顺序、类型、不可变性和异常传播测试通过。

**关键设计决策：** pipeline 不拥有 runtime、设备或持久化；result 使用不可变
commands/events。

## TASK-004

**目标：** 建立事件日志和确定性重放边界。

**实现内容：** 引入 `EventRecord`、`EventJournal`、sequence 和 replay。

**架构意义：** 把事件历史和可重放证据提升为一等架构能力。

**新增文件：** `kernel/event/*`、事件日志/重放测试及 ADR。

**验证结果：** 序列、追加不可变性、事件身份和 replay 回归通过。

**关键设计决策：** journal append 返回新 journal；replay 观察已有记录，不执行
策略或设备。

## TASK-005

**目标：** 建立确定性 Runtime Kernel Tick。

**实现内容：** 引入 `RuntimeKernel` 和不可变 `TickResult`。

**架构意义：** 明确 runtime 是状态推进的所有者，decision pipeline 保持独立。

**新增文件：** `kernel/runtime/kernel.py`、`tick.py`、测试和 ADR。

**验证结果：** tick 调用、结果身份、不可变性和回归检查通过。

**关键设计决策：** 一次 tick 是确定性执行单元；不加入循环、线程、计时器或设备。

## TASK-006

**目标：** 建立能源资产领域基础。

**实现内容：** 引入 `EnergyAsset`、`BatteryAsset`、`PVAsset`、`LoadAsset`。

**架构意义：** 分离物理资产定义和后续运行状态、策略与控制。

**新增文件：** `kernel/asset/*`、资产测试、`ADR-005`。

**验证结果：** 类型、范围、冻结、slots 和 public imports 测试通过。

**关键设计决策：** 资产只描述能力，不包含 SOC、SOH、遥测或控制行为。

## TASK-007

**目标：** 建立第一代不可变能源状态快照。

**实现内容：** 引入 battery/PV/load state 和 `EnergySnapshot`。

**架构意义：** 把资产定义与当前观察分离，为确定性决策输入提供基础。

**新增文件：** `kernel/state/*`、状态测试、`ADR-006`。

**验证结果：** 范围、tuple、排序、不可变性和完整回归通过。

**关键设计决策：** 状态不做 SOC 计算、预测、通信或持久化。

## TASK-008

**目标：** 建立不可变功率流模型。

**实现内容：** 引入 `PowerFlow`，验证 PV、负荷、电池、电网功率及功率平衡。

**架构意义：** 固化功率符号和守恒关系，避免策略隐式解释方向。

**新增文件：** `kernel/power/*`、功率流测试、`ADR-007`。

**验证结果：** 有限数值、bool 拒绝、符号、平衡容差和不可变性测试通过。

**关键设计决策：** PowerFlow 是观察，不自动修正、不执行控制。

## TASK-009

**目标：** 建立 immutable `EnergySystemContext`。

**实现内容：** 聚合 assets、states 和 `PowerFlow`，验证资产状态匹配。

**架构意义：** 为 legacy EMS 决策提供一个统一、确定性的输入边界。

**新增文件：** `kernel/context/*`、context tests、`ADR-008`。

**验证结果：** 类型、匹配、顺序、identity 和 tuple protection 测试通过。

**关键设计决策：** 保留调用方顺序，不排序、不去重、不隐藏计算。

## TASK-010

**目标：** 建立 legacy EMS policy 接口边界。

**实现内容：** 定义抽象 `EMSPolicy.evaluate(EnergySystemContext) -> DecisionResult`。

**架构意义：** 为未来算法提供可替换的 legacy 扩展点。

**新增文件：** `kernel/policy/base.py`、policy tests、`ADR-009`。

**验证结果：** abstract signature、不可直接实例化和无状态合同测试通过。

**关键设计决策：** policy 不拥有 clock、scheduler、storage、通信或设备。

## TASK-011

**目标：** 建立 policy execution adapter。

**实现内容：** 引入无状态 `PolicyExecutor`。

**架构意义：** 把 policy 调用从 lifecycle 对象中抽离并统一验证返回类型。

**新增文件：** `kernel/execution/executor.py`、execution tests、`ADR-010`。

**验证结果：** 正常执行、替换、context identity 和异常传播测试通过。

**关键设计决策：** executor 不保存 policy，不修改 context，不吞掉异常。

## TASK-012

**目标：** 建立一次 EMS 决策周期。

**实现内容：** 引入 immutable `EMSCycle`，通过 `PolicyExecutor` 创建。

**架构意义：** 把 context 与 exact result 组合为一次确定性生命周期单元。

**新增文件：** `kernel/cycle/cycle.py`、cycle tests、`ADR-011`。

**验证结果：** 单次执行、exact identity、冻结和异常传播测试通过。

**关键设计决策：** cycle 不保存 policy，不直接调用 policy，不实现 runtime loop。

## TASK-013

**目标：** 把 EMSCycle 的事件记录到 immutable EventJournal。

**实现内容：** 引入 `JournaledEMSCycle.record()`。

**架构意义：** 关联 exact cycle 与确定性递增的事件日志。

**新增文件：** `kernel/cycle/journal.py`、journaled cycle tests、`ADR-012`。

**验证结果：** sequence、事件顺序/身份、空事件 identity 和命令不入日志测试通过。

**关键设计决策：** 只 journal events，不处理 commands；原 journal 保持不变。

## TASK-014

**目标：** 建立 journaled EMS execution service。

**实现内容：** 组合 policy execution、cycle creation 和 event journaling。

**架构意义：** 为一次带事件证据的 legacy EMS 执行提供无状态入口。

**新增文件：** `kernel/execution/service.py`、service tests、`ADR-013`。

**验证结果：** 调用顺序、单次执行、identity、空事件和异常传播测试通过。

**关键设计决策：** 复用已有 executor/cycle/journal，不重新实现阶段逻辑。

## TASK-015

**目标：** 建立 journaled EMS runtime tick。

**实现内容：** 引入 `JournaledEMSTick` 和 `JournaledEMSRuntime.tick()`。

**架构意义：** 把一次 journaled execution 提升为 runtime 可观察 tick。

**新增文件：** `kernel/runtime/journaled.py`、runtime tick tests、`ADR-014`。

**验证结果：** tick identity、事件日志、异常传播和回归测试通过。

**关键设计决策：** tick 仍是单次调用，不引入循环、scheduler 或设备。

## TASK-016

**目标：** 建立 runtime tick progression。

**实现内容：** 从前一 journaled tick 和新输入生成下一 tick。

**架构意义：** 明确 immutable runtime 生命周期如何前进。

**新增文件：** progression 生产接口、tests、`ADR-015`。

**验证结果：** previous/current identity、journal continuity 和失败行为测试通过。

**关键设计决策：** progression 返回新对象，不修改前一 tick 或 journal。

## TASK-017

**目标：** 建立 command dispatch 接口边界。

**实现内容：** 定义抽象 `CommandDispatcher.dispatch(Command) -> None`。

**架构意义：** 隔离 immutable domain Command 与未来外部设备 adapter。

**新增文件：** `kernel/dispatch/dispatcher.py`、dispatch tests、`ADR-016`。

**验证结果：** abstract contract、exact command identity、异常传播和空 slots 测试通过。

**关键设计决策：** 不定义重试、timeout、batch、receipt、协议或设备实现。

## TASK-018

**目标：** 建立确定性 command executor。

**实现内容：** 引入 `CommandExecutor`，按 tuple 顺序逐个调用 dispatcher。

**架构意义：** 把命令集合遍历与具体 dispatcher 实现分离。

**新增文件：** `kernel/dispatch/executor.py`、executor tests、`ADR-017`。

**验证结果：** 顺序、exact identity、停止于首个异常和无状态测试通过。

**关键设计决策：** 不重试、不并行、不修改、不 journal commands。

## TASK-019

**目标：** 建立 dispatched journaled runtime tick。

**实现内容：** 引入 `DispatchedJournaledEMSTick` 和 runtime dispatch 边界。

**架构意义：** 显式区分“已决策/记录”和“已完成 dispatch”的生命周期阶段。

**新增文件：** runtime dispatch models/methods、tests、`ADR-018`。

**验证结果：** tick identity、command identity、异常传播和不可变性测试通过。

**关键设计决策：** dispatched tick 是观察证据，不保存 dispatcher。

## TASK-020

**目标：** 建立 dispatch 后 progression 合同。

**实现内容：** 规定只有完成 dispatch 的 tick 才能进入下一 progression。

**架构意义：** 用类型和身份关系固定 dispatch-before-progress 顺序。

**新增文件：** dispatch progression contract、tests、`ADR-019`。

**验证结果：** 合法 progression、错误阶段拒绝和 identity 测试通过。

**关键设计决策：** 不改变 TASK-015/016/019 既有合同，不引入重试或 rollback。

## TASK-021

**目标：** 建立 dispatch progression runtime integration。

**实现内容：** 无状态组合 tick、journal、dispatch 和 progression。

**架构意义：** 为 legacy 路径提供完整、固定顺序的 deterministic runtime cycle。

**新增文件：** `kernel/runtime/integration.py`、integration tests、`ADR-020`。

**验证结果：** 阶段顺序、每阶段一次、dispatch/decision failure short-circuit 测试通过。

**关键设计决策：** 只复用已有组件，不缓存 runtime state，不接入设备协议。

## TASK-022

**目标：** 建立 deterministic runtime execution trace。

**实现内容：** 引入 immutable `RuntimeExecutionTrace`。

**架构意义：** 保存 source、dispatched 和 progressed tick 的 exact 生命周期关系。

**新增文件：** `kernel/runtime/trace.py`、trace tests、`ADR-021`。

**验证结果：** frozen/slotted、身份链、结构完成验证和无副作用测试通过。

**关键设计决策：** trace 是观察，不是 runtime state；不生成 timestamp/UUID。

## TASK-023

**目标：** 建立 deterministic replay boundary。

**实现内容：** 引入 immutable `ReplayResult` 和 stateless `RuntimeReplay`。

**架构意义：** 观察已完成 trace，而不重新执行 policy、dispatch 或 progression。

**新增文件：** `kernel/runtime/replay.py`、replay tests、`ADR-022`。

**验证结果：** identity、确定性、无执行调用、无 journal mutation 测试通过。

**关键设计决策：** Replay != Re-execution。

## TASK-024

**目标：** 建立 execution audit boundary。

**实现内容：** 引入 immutable `ExecutionAudit`。

**架构意义：** 在 trace 之上提供只读、身份驱动的审计观察。

**新增文件：** `kernel/runtime/audit.py`、audit tests、`ADR-023`。

**验证结果：** trace/tick identity、深层不可变、无副作用和无状态保留测试通过。

**关键设计决策：** audit 不调用 replay、不持久化、不诊断、不修复。

## TASK-025

**目标：** 建立 decision explanation boundary。

**实现内容：** 引入 immutable `DecisionExplanation`，公开 `source_context`。

**架构意义：** 关联 audit、trace、源 context 和 decision result，而不重算决策。

**新增文件：** `kernel/runtime/explanation.py`、explanation tests、`ADR-024`。

**验证结果：** public contract、identity、不可变、无执行和完整回归通过。

**关键设计决策：** explanation 不生成原因、建议或 derived analysis；不保留 `context`
兼容 alias。

## TASK-026

**目标：** 建立不可变 Decision Context Boundary。

**实现内容：** 定义时间、SOC、容量、功率、电价和约束字段。

**架构意义：** 固化“决策发生时系统看到的世界”，为新 EMS policy 路径提供输入。

**新增文件：** `kernel/decision/context.py`、validation/tests、`ADR-025`。

**验证结果：** 类型、范围、时区、单位、grid sign 和 immutable tests 通过。

**关键设计决策：** 电价命名为 `electricity_price_cny_per_kwh`；grid 正值进口、负值
出口；context 不包含 decision、command 或 forecast。

## TASK-027

**目标：** 建立 Energy System State Boundary。

**实现内容：** 定义 `BatteryState`、`PCSState`、`PVState`、`GridState` 和
`EnergySystemState`。

**架构意义：** 形成新决策路径的物理观测层，严格分离物理事实与决策输入。

**新增文件：** `kernel/system_state/*`、`tests/unit/system_state/*`、
`tasks/TASK-027.md`、`ADR-026`。

**验证结果：** frozen/slotted、单位、范围、符号、组件 identity、dependency isolation
和完整回归通过。

**关键设计决策：** aggregate 公共字段固定为 `battery`、`pcs`、`pv`、`grid`；无旧名
alias；PCS 正值表示 AC 输出，grid 正值表示进口。

## TASK-028

**目标：** 建立 `EnergySystemState -> DecisionContext` 装配边界。

**实现内容：** 引入无状态 `DecisionContextAssembler`。

**架构意义：** 明确物理状态映射与外部决策事实的来源，防止隐式推导。

**新增文件：** `kernel/decision/assembler.py`、assembler tests、
`tasks/TASK-028.md`、`ADR-027`。

**验证结果：** direct mapping、required keyword-only inputs、无 mutation、无 cache 和
完整回归通过。

**关键设计决策：** SOC、PV actual power、grid power 直接映射；时间、功率限制、
容量、负荷、电价、reserve/export limit 全由调用者显式提供。

## TASK-029

**目标：** 建立新的 DecisionContext Policy Boundary。

**实现内容：** 定义抽象 `DecisionContextPolicy`。

**架构意义：** 在不迁移 legacy 路径的前提下，为新 DecisionContext 输入建立策略扩展点。

**新增文件：** `kernel/policy/decision_context.py`、policy tests、
`tasks/TASK-029.md`、`ADR-028`。

**验证结果：** abstract signature、无状态、public import、legacy independence 和完整
回归通过；当时记录为 618 tests passed。

**关键设计决策：** 不继承、不 adapter、不 overload `EMSPolicy`；两条 policy 合同并存。

## TASK-030

**目标：** 建立新策略路径的 immutable result boundary。

**实现内容：** 引入 `DecisionContextResult`，并让 `DecisionContextPolicy` 返回该类型。

**架构意义：** 把新策略的语义输出与 legacy commands/events 输出彻底分离。

**新增文件：** `kernel/decision/context_result.py`、result tests、
`tasks/TASK-030.md`、`ADR-029`。

**验证结果：** frozen/slotted、无 mutable fields、public API、legacy regression 通过。

**关键设计决策：** legacy `DecisionResult` 不变；新 result 不包含 commands、events 或
execution state。

## TASK-031

**目标：** 建立 Decision Intent Boundary。

**实现内容：** 引入 immutable `DecisionIntent`，并由 `DecisionContextResult` 保存。

**架构意义：** 在策略输出与未来命令生成之间建立纯语义层。

**新增文件：** `kernel/decision/intent.py`、intent/result tests、
`tasks/TASK-031.md`、`ADR-030`。

**验证结果：** 有限数值、frozen/slotted、无 `__dict__`、identity 和 dependency tests
通过。

**关键设计决策：** `battery_power_intent_kw` 是原始 kW；正值充电、负值放电、零空闲；
不在 intent 中放置 PCS/CAN/Modbus 信息。

## TASK-032

**目标：** 建立 Decision Constraint Boundary。

**实现内容：** 定义抽象 `DecisionConstraintBoundary` 和 immutable
`FeasibleDecisionIntent`。

**架构意义：** 分离策略意图与物理可行性，避免 policy 隐藏 clipping 或 SOC 控制。

**新增文件：** `kernel/decision/constraint.py`、constraint tests、
`tasks/TASK-032.md`、`ADR-031`。

**验证结果：** abstract contract、intent identity、immutability、dependency isolation
和完整回归通过。

**关键设计决策：** TASK 只建立 seam，不实现 SOC、功率限制、优化或预测算法。

## TASK-033

**目标：** 建立 Constraint Explanation Boundary。

**实现内容：** 引入 immutable `ConstraintExplanation`。

**架构意义：** 用只读关系对象连接 policy source intent 与 feasible intent。

**新增文件：** `kernel/decision/constraint_explanation.py`、explanation tests、
`tasks/TASK-033.md`、`ADR-032`。

**验证结果：** exact identity、frozen/slotted、无 derived analysis、public API 和完整
回归通过。

**关键设计决策：** explanation 不生成理由、建议或结论；只保存既有对象引用。

## TASK-034

**目标：** 建立 Decision Evaluation Cycle Boundary。

**实现内容：** 引入 immutable `DecisionEvaluationCycle`。

**架构意义：** 把 context、result、source intent、feasible intent 和 explanation
组织为一次完整评估证据。

**新增文件：** `kernel/decision/evaluation_cycle.py`、cycle tests、
`tasks/TASK-034.md`、`ADR-033`。

**验证结果：** 667 tests passed；Ruff、mypy、GitHub Actions 通过。

**关键设计决策：** 使用 `is` 分别验证 source 与 feasible lineage；cycle 不执行
policy/constraint，不保存实现实例。

## TASK-035

**目标：** 建立 Decision Evaluation Orchestration Boundary。

**实现内容：** 引入无状态 `DecisionEvaluationOrchestrator`。

**架构意义：** 固定 assembler、policy、constraint、explanation 和 cycle 的调用顺序。

**新增文件：** `kernel/policy/orchestration.py`、orchestration tests、
`tasks/TASK-035.md`、`ADR-034`。

**验证结果：** 679 tests passed；Ruff、mypy、GitHub Actions 通过。

**关键设计决策：** policy/constraint 由调用者提供且不留存；所有外部事实是 required
keyword-only inputs；不接入 runtime 或 device。

## TASK-036

**目标：** 建立 EMS Policy Implementation Boundary。

**实现内容：** 引入抽象 `DecisionContextPolicyImplementation`。

**架构意义：** 为未来具体 EMS 策略提供明确扩展点，同时保持
`DecisionContextPolicy` 和 legacy `EMSPolicy` 稳定。

**新增文件：** `kernel/policy/implementation.py`、implementation tests、
`tasks/TASK-036.md`、`ADR-035`。

**验证结果：** 687 tests passed；Ruff、mypy、GitHub Actions 通过。

**关键设计决策：** implementation boundary 继承既有 evaluate 合同但不实现算法；
空 slots、无状态、无新输出类型、无 legacy migration。

## TASK-037 Self Consumption EMS Policy

**目标：**

实现第一个具体 EMS 策略。

**实现内容：**

新增 `SelfConsumptionPolicy`，继承
`DecisionContextPolicyImplementation`，实现：

```python
evaluate(
    context: DecisionContext,
) -> DecisionContextResult
```

**架构意义：**

TASK-001～036 建立决策基础设施，TASK-037 首次引入实际能源管理逻辑。它验证具体
算法可以运行在既有不可变边界之上，而无需修改 Decision、Constraint、Runtime 或
Execution 架构。

**输入：**

`DecisionContext`

**使用：**

- `pv_power_kw`
- `load_power_kw`

**输出：**

`DecisionIntent`。公开 evaluate 合同通过 `DecisionContextResult` 返回该 exact
intent 引用。

**语义：**

正值：

电池充电意图。

负值：

电池放电意图。

零值：

电池空闲意图。

基础规则：

```text
PV > Load -> +(PV - Load)
PV < Load -> -(Load - PV)
PV = Load -> 0
```

**刻意不包含：**

- SOC 限制
- 电池功率限制
- PCS 控制
- 设备命令
- dispatch 或 runtime 调用
- 优化、预测或 TOU 策略

**原因：**

保持 Policy 和 Constraint 职责分离。Policy 只表达能源管理意图，Constraint 判断
物理可行性，未来 Execution/Device 层负责把可行意图转换为外部动作。

**新增文件：**

`kernel/policy/self_consumption.py`、专项测试、`tasks/TASK-037.md` 和
`ADR-036-self-consumption-policy.md`。

**验证结果：**

701 tests passed；Ruff、mypy 和 GitHub Actions 通过。

**关键设计决策：**

只使用当前 PV 与负荷功率；不读取价格、grid、SOC 或 power limit；策略创建的
`DecisionIntent` 原始引用直接进入 `DecisionContextResult`。

## TASK-038 Battery Constraint Implementation

**目标：**

实现第一个具体物理约束层，在不修改通用 boundary 的前提下判断电池意图是否可行。

**实现内容：**

新增 frozen、slotted 的 `BatteryConstraintImplementation`，继承
`DecisionConstraintBoundary` 并保持：

```python
evaluate(intent: DecisionIntent) -> FeasibleDecisionIntent
```

**输入：**

- 原始 `DecisionIntent`
- 构造阶段注入的 `soc`
- `reserve_soc`
- `max_charge_power_kw`
- `max_discharge_power_kw`

SOC 使用 `[0, 1]` 无量纲比例，功率使用未经缩放的 kW。

**输出：**

`FeasibleDecisionIntent`。

**约束规则：**

- 满电时禁止继续充电；
- SOC 位于或低于 reserve SOC 时禁止继续放电；
- 充放电意图超过对应功率上限时执行确定性裁剪；
- 零意图保持不变。

**架构意义：**

这是 EOS 第一个物理约束实现。TASK-001～037 建立决策基础设施；TASK-037 的 Policy
首次产生真实能源管理意图；TASK-038 的 Constraint 首次根据电池物理限制，将策略
意图转换为可行意图。

```text
DecisionIntent
        |
        v
BatteryConstraintImplementation
        |
        v
FeasibleDecisionIntent
```

Policy 负责根据能源状态产生意图，不负责 SOC 限制、电池功率限制或设备能力判断。
Constraint 负责将意图限制在物理可行范围。Battery-specific facts 不会泄漏到通用
`DecisionConstraintBoundary` 或 Orchestrator。

**Identity：**

未修改的意图保持 exact identity。被禁止或裁剪时创建新的 immutable intent，原始
`DecisionIntent` 不被修改。

**刻意不包含：**

- SOC 计算或预测
- EMS 策略
- runtime 执行、dispatch 或 persistence
- PCS 或 BMS 控制
- CAN、Modbus 或 device command
- optimization 或 forecasting
- cache、history 或 mutable runtime state

**新增文件：**

`kernel/decision/battery_constraint.py`、专项单元测试、`tasks/TASK-038.md` 和
`architecture/adr/ADR-037-battery-constraint-boundary.md`。

**验证结果：**

730 tests passed；Ruff check、Ruff format 和 mypy 通过。

**关键设计决策：**

约束事实通过构造阶段注入 frozen implementation；通用 `evaluate(intent)` 契约和
`DecisionEvaluationOrchestrator` 保持不变。

## TASK-039 Decision Intent Lineage

**目标：**

修复 `DecisionEvaluationCycle` 对 policy source intent 与 constraint feasible intent
错误要求同一身份的问题。

**实现内容：**

- 将 Cycle 公共字段 `intent` 重命名为 `source_intent`；
- `source_intent` 必须是 `DecisionContextResult.intent` 的 exact reference；
- 保留 exact `FeasibleDecisionIntent`；
- `ConstraintExplanation.create()` 显式接收 source 与 feasible artifacts；
- 不提供旧 `intent` 字段的兼容 alias。

**架构意义：**

TASK-038 首次允许 Constraint 在阻止或裁剪时创建新的 immutable intent。TASK-039
因此把一条含糊的单身份链升级为两条明确 lineage：

```text
DecisionContextResult.intent
        |
        v
source_intent

DecisionConstraintBoundary output
        |
        v
FeasibleDecisionIntent.intent
```

未调整时，两条 lineage 指向同一 `DecisionIntent`；调整时，它们指向两个不同但均为
exact、immutable 的对象。

**新增文件：**

`tasks/TASK-039.md` 和
`architecture/adr/ADR-038-decision-intent-lineage.md`。

**验证内容：**

- 无裁剪时 source/feasible identity 保持；
- Battery Constraint 裁剪后 Cycle 正常创建；
- source intent lineage 正确；
- feasible intent lineage 正确；
- legacy、runtime 和 execution 路径保持不变。

**关键设计决策：**

不修改 `DecisionIntent`、`DecisionConstraintBoundary`、Policy 职责或 Constraint
职责；Cycle 仍是 frozen、slotted、observation-only 生命周期边界。

## TASK-040 Grid Constraint Boundary

**目标：**

建立并网侧物理约束的抽象扩展入口，不实现具体限制算法。

**实现内容：**

- 新增 abstract、stateless `GridConstraintBoundary`；
- 继承现有 `DecisionConstraintBoundary`；
- 保持 `evaluate(intent: DecisionIntent) -> FeasibleDecisionIntent` 签名；
- 通过 `kernel.decision` 提供公开导入；
- 不在抽象边界中保存任何 grid facts。

**架构意义：**

TASK-038 建立第一个电池物理约束实现，TASK-039 稳定 source/feasible lineage。
TASK-040 将并网侧物理能力定义为独立扩展方向：

```text
source DecisionIntent
        |
        v
GridConstraintBoundary
        |
        v
FeasibleDecisionIntent
```

Battery Constraint 与 Grid Constraint 共享通用 constraint 契约，但分别拥有不同的
物理事实和未来实现，避免把 grid import/export capability 泄漏到电池约束、Policy
或 Orchestrator。

**新增文件：**

- `kernel/decision/grid_constraint.py`；
- `tests/unit/decision/test_grid_constraint.py`；
- `tasks/TASK-040.md`；
- `architecture/adr/ADR-039-grid-constraint-boundary.md`。

**验证内容：**

- boundary 是 abstract、empty-slotted 和 stateless；
- evaluate 签名与通用 constraint contract 完全一致；
- public import 可用；
- 无具体生产实现、grid facts、算法或 forbidden dependencies；
- intent、policy、lineage、legacy、runtime 和 execution 契约保持不变。

**关键设计决策：**

未来具体 Grid Constraint 可以通过构造阶段接收 immutable import/export limits 或
zero-export capability，但 TASK-040 不定义这些 facts 的字段、单位、范围或算法。
本任务不实现 zero export、TOU、optimization、forecast、PCS/device control、
dispatch、runtime、persistence、cache 或 history。

## TASK-041 Grid Power Limit Constraint Implementation

**目标：**

实现第一个具体 Grid Constraint，根据显式并网基准功率和进出口功率上限产生可行的
battery intent。

**实现内容：**

- 新增 frozen、slotted `GridPowerLimitConstraintImplementation`；
- 继承 `GridConstraintBoundary`；
- 构造注入 `grid_power_baseline_kw`、`max_import_power_kw` 和
  `max_export_power_kw`；
- 保持通用 `evaluate(intent) -> FeasibleDecisionIntent` 契约；
- 通过 `kernel.decision` 提供公开导入。

**架构意义：**

TASK-040 只建立 Grid Constraint 抽象入口。TASK-041 首次在该入口上实现确定性的
并网功率物理限制：

```text
source DecisionIntent
        |
        v
GridPowerLimitConstraintImplementation
        |
        v
FeasibleDecisionIntent
```

`DecisionIntent` 仍只表示 battery power。Grid constraint 使用显式 baseline 将
battery intent 投影为 grid power，避免把两种功率语义混为一谈。

**物理契约：**

- `grid_power_baseline_kw`：应用 battery intent 前的并网功率，正值进口、负值出口；
- battery intent：正值充电、负值放电；
- projected grid power：`baseline + battery intent`；
- 允许区间：`[-max_export_power_kw, max_import_power_kw]`；
- 所有数值均为未经缩放的 kW。

**Identity：**

无调整时保留 exact source intent；发生限制时创建新的 immutable intent，并保持原始
Policy intent 不变。TASK-039 lineage contract 不变。

**新增文件：**

- `kernel/decision/grid_power_limit_constraint.py`；
- `tests/unit/decision/test_grid_power_limit_constraint.py`；
- `tasks/TASK-041.md`；
- `architecture/adr/ADR-040-grid-power-limit-constraint.md`。

**验证内容：**

- import/export limits 的确定性限制；
- baseline、limits 的类型、有限值、单位和范围；
- 无调整与调整场景的 identity；
- frozen/slotted 和无 mutable state；
- public import 与 dependency isolation；
- Policy、boundary、lineage、legacy、runtime 和 execution 保持不变。

**关键设计决策：**

不向 `DecisionIntent` 添加 grid 字段，不把 battery intent 解释为 grid power，也不让
Policy 获取 grid limits。本任务没有专用 Zero Export 策略、TOU、电价、optimization、
forecast、PCS/device control、runtime、persistence、cache 或 history。

## TASK-042 Constraint Composition Boundary

**目标：**

建立多个 `DecisionConstraintBoundary` 的确定性组合入口。

**实现内容：**

- 新增 stateless、empty-slotted `ConstraintEvaluationPipeline`；
- 接收 exact source `DecisionIntent`；
- 接收 caller-supplied immutable constraint tuple；
- 按 tuple 顺序依次调用；
- 返回最后一阶段的 exact `FeasibleDecisionIntent`；
- 通过 `kernel.decision` 提供公开导入。

**架构意义：**

TASK-038 和 TASK-041 分别提供 Battery 与 Grid concrete constraints。TASK-042 定义
这些独立能力如何形成一条确定性可行性链：

```text
source DecisionIntent
        |
        v
ConstraintEvaluationPipeline
        |
        +--> Constraint[0]
        |
        +--> Constraint[1]
        |
        v
final FeasibleDecisionIntent
```

Constraint 顺序由调用者显式提供，Policy 不选择也不感知顺序。Pipeline 不拥有或保存
constraint instances。

**Identity：**

- source intent 不复制或修改；
- 每一阶段接收上一阶段 exact inner intent；
- 最终 wrapper 保持最后一阶段 exact identity；
- 所有阶段未调整时，最终 inner intent 保持 source identity；
- 空 tuple 返回引用 source intent 的 wrapper。

**新增文件：**

- `kernel/decision/constraint_pipeline.py`；
- `tests/unit/decision/test_constraint_pipeline.py`；
- `tasks/TASK-042.md`；
- `architecture/adr/ADR-041-constraint-composition-boundary.md`。

**验证内容：**

- caller order 与 exactly-once execution；
- stage-to-stage exact identity；
- empty composition；
- 不排序、不去重；
- exception propagation 与 failure short-circuit；
- tuple、member 和 result type validation；
- public import、empty slots 与 dependency isolation；
- Policy、boundary、lineage、legacy、runtime 和 execution 保持不变。

**关键设计决策：**

Pipeline 是无状态 composition boundary，不是 optimization 或 constraint strategy。
本任务不实现 priority、conflict resolution、MPC、forecast、TOU、pricing、runtime、
commands、dispatch、device control、persistence、cache 或 history。

## TASK-043 Constraint Explanation Chain Boundary

**目标：**

建立多个 completed Constraint stage 的 immutable、有序解释证据边界。

**实现内容：**

- 新增 frozen/slotted `ConstraintExplanationEntry`；
- 保存 exact stage source intent；
- 保存 exact stage `FeasibleDecisionIntent`；
- 记录 identity-based `adjusted`；
- 保存 caller-supplied opaque `adjustment_reason`；
- 新增 frozen/slotted `ConstraintExplanationChain`；
- 使用 tuple 保存多个 Entry 的权威顺序；
- 验证逐阶段 identity continuity；
- 通过 `kernel.decision` 提供公开导入。

**架构意义：**

TASK-042 定义约束如何按序执行，TASK-043 定义如何在不重新执行的情况下观察每一阶段：

```text
source DecisionIntent
        |
        v
ConstraintEvaluationPipeline
        |
        v
final FeasibleDecisionIntent
        |
        v
ConstraintExplanationChain
        |
        +--> ConstraintExplanationEntry[0]
        |
        +--> ConstraintExplanationEntry[1]
```

**Identity：**

- Entry source/feasible references 不复制、不重建；
- `adjusted` 等价于 feasible inner intent 与 stage source 是否为不同对象；
- 下一 Entry source 必须是上一 Entry 的 exact feasible inner intent；
- Chain final feasible 必须是最后 Entry 的 exact wrapper；
- 空 Chain 通过 feasible wrapper 保持 source intent identity；
- entries tuple 和其中 Entry 均保持 exact identity。

**Reason contract：**

Reason 由调用者显式提供。调整时必须是非空字符串，未调整时必须为 `None`。Artifact
不生成、标准化、解释或分析 reason，也不读取 SOC、功率、电网、价格或设备状态推理
原因。

**新增文件：**

- `kernel/decision/constraint_explanation_chain.py`；
- `tests/unit/decision/test_constraint_explanation_chain.py`；
- `tasks/TASK-043.md`；
- `architecture/adr/ADR-042-constraint-explanation-chain-boundary.md`。

**验证内容：**

- adjusted/unchanged stage identity；
- caller-supplied reason contract；
- multi-stage order 与 exact continuity；
- empty chain；
- broken first/intermediate/final identity rejection；
- frozen/slotted、tuple-only 与无 mutable state；
- observation-only dependency isolation；
- public imports；
- 既有 Constraint、Intent、Explanation、Cycle、Policy、legacy、runtime 和 execution
  契约不变。

**关键设计决策：**

不修改 TASK-033 `ConstraintExplanation`，不让
`DecisionConstraintBoundary.evaluate()` 返回 reason，也不让 Chain 调用 Pipeline。
本任务没有 derived reasoning、constraint algorithm、TOU、pricing、optimization、
MPC、forecast、runtime、dispatch、device control、persistence、cache 或 history。

## TASK-044 Decision Evaluation Integration Boundary

**目标：**

将现有新决策组件组合为一次完整、确定性、exactly-once 的评估流程。

**实现内容：**

- 新增 stateless `DecisionEvaluationIntegration`；
- 组合 `DecisionContextAssembler` 与 caller-supplied Policy；
- 调用 `ConstraintEvaluationPipeline` exactly once；
- 保证每个 caller constraint exactly once；
- 在同一次执行中形成 ordered `ConstraintExplanationEntry` tuple；
- 创建 exact `ConstraintExplanationChain`；
- 复用既有 `ConstraintExplanation` 与 `DecisionEvaluationCycle`；
- 新增 frozen/slotted `DecisionEvaluationIntegrationResult`；
- Result 同时保存 exact cycle 与 exact explanation chain；
- 通过 `kernel.policy` 提供公开导入。

**架构意义：**

```text
EnergySystemState
        |
        v
DecisionContextAssembler
        |
        v
DecisionContextPolicy
        |
        v
DecisionIntent
        |
        v
ConstraintEvaluationPipeline
        |
        v
ConstraintExplanationChain
        |
        v
DecisionEvaluationCycle
        |
        v
DecisionEvaluationIntegrationResult
```

TASK-044 让 TASK-028、029、042、043 和 034 的独立边界形成一个可调用入口，但不迁移
旧 Orchestrator、legacy Policy 或 runtime/execution。

**Exactly once 与 Identity：**

- assembled context 是 Policy 收到的 exact object；
- Pipeline 接收 exact policy intent；
- Pipeline 只调用一次；
- 每个 Constraint 只调用一次；
- 下一 Constraint 接收上一阶段 exact feasible inner intent；
- Entry 保存 exact stage input/output；
- Chain 保存 exact entries tuple 和 final wrapper；
- Cycle 保存 exact context/result/source/final feasible；
- Integration Result 保存 exact Cycle 与 Chain。

**Reason ownership：**

Caller 提供与 constraint tuple 等长的 reason tuple。Reason 只在该阶段 identity 发生
变化时写入 Entry；未调整时写入 `None`。Integration 不从 SOC、Grid、电价或设备状态
自动生成 reason。

**新增文件：**

- `kernel/policy/integration.py`；
- `tests/unit/policy/test_integration.py`；
- `tasks/TASK-044.md`；
- `architecture/adr/ADR-043-decision-evaluation-integration-boundary.md`。

**验证内容：**

- 完整 context-to-cycle identity；
- multi-constraint order 与 lineage；
- component exactly-once；
- empty pipeline；
- caller reason ownership；
- policy/constraint failure short-circuit；
- invalid configuration/result validation；
- immutable exact integration result；
- statelessness、dependency isolation 与 public import；
- Intent、Constraint、Pipeline、Explanation、Cycle、Policy、legacy、runtime 和 execution
  contracts 保持不变。

**关键设计决策：**

不修改 Pipeline 返回类型，不修改 Cycle 字段，不修改旧 Orchestrator。Integration 使用
private immutable observing decorator 捕获同一次 Pipeline 执行的阶段证据，并只在
调用栈内使用 immutable tuple，不保存 cache/history/runtime state。本任务没有 EMS
strategy、optimization、MPC、forecast、TOU、pricing、runtime、dispatch、device
control 或 persistence。

## TASK-045 EMS Capability Layer Boundary

**目标：**

建立 Phase 3 EMS Capability Layer 的第一个抽象业务能力扩展入口。

**实现内容：**

- 新增 abstract、empty-slotted `EMSCapabilityBoundary`；
- 定义 `evaluate(DecisionContext) -> DecisionIntent`；
- 通过顶层 `capability` package 提供公开导入；
- 不实现任何 concrete capability 或 EMS algorithm；
- 不接入现有 Policy、Constraint Pipeline 或 Evaluation Integration。

**架构意义：**

```text
DecisionContext
        |
        v
EMSCapabilityBoundary
        |
        v
DecisionIntent
        |
        v
future reviewed composition
```

TASK-001～044 建立稳定 Kernel、Constraint 与 Evaluation Framework。TASK-045 开始
Phase 3，使业务能力可以在不修改 Kernel 架构的前提下演进。

Capability 表达业务目标希望系统做什么；Constraint 继续决定物理上允许什么；Runtime、
Dispatch 和 Device 继续负责后续执行职责。

**Public contract：**

```python
class EMSCapabilityBoundary(ABC):
    __slots__ = ()

    @abstractmethod
    def evaluate(
        self,
        context: DecisionContext,
    ) -> DecisionIntent:
        raise NotImplementedError
```

**新增文件：**

- `capability/base.py`；
- `tests/unit/capability/test_boundary.py`；
- `tasks/TASK-045.md`；
- `architecture/adr/ADR-044-ems-capability-layer-boundary.md`。

**验证内容：**

- boundary abstract；
- evaluate 签名与类型合同；
- exact context 与 intent identity；
- empty slots、无 `__dict__` 和无 mutable state；
- 与 `DecisionContextPolicy` 相互独立；
- 无 runtime、dispatch、device、persistence、optimization 或 forecast 依赖；
- public import 只导出 `EMSCapabilityBoundary`；
- 既有 Intent、Policy、Constraint、Integration、legacy、runtime 和 execution 合同不变。

**关键设计决策：**

`EMSCapabilityBoundary` 不继承 `DecisionContextPolicy`，也不返回
`DecisionContextResult`，从而避免在 boundary introduction task 中迁移 Policy。
TASK-045 不定义 Capability 如何进入现有 Evaluation Integration；该组合需要未来独立
review。边界不包含 SOC、功率、Grid limit、PCS/BMS、command、runtime、dispatch、
optimization、forecast、cache 或 history。

## TASK-046 TOU Energy Capability

**目标：**

在 Phase 3 `EMSCapabilityBoundary` 上实现第一个具体 EMS Capability。

**实现内容：**

- 新增 frozen/slotted `TOUCapabilityParameters`；
- 显式保存 charge/discharge 本地小时 tuple；
- 显式保存 CNY/kWh charge ceiling 与 discharge floor；
- 显式保存非负 raw kW charge/discharge intent magnitudes；
- 新增 frozen/slotted `TOUEnergyCapability`；
- 根据 exact `DecisionContext.timestamp.hour` 和
  `electricity_price_cny_per_kwh` 生成 `DecisionIntent`；
- 通过顶层 `capability` package 提供公开导入。

**架构意义：**

```text
DecisionContext
        |
        v
TOUEnergyCapability
        |
        v
DecisionIntent
        |
        v
existing Constraint and Evaluation boundaries
```

TASK-046 证明 concrete EMS 业务能力可以在顶层 capability package 独立演进，而不
修改 Kernel、Policy、Constraint、Evaluation、Runtime 或 Device contracts。

**确定性规则：**

- charge hour 且 price <= charge ceiling：positive charging intent；
- discharge hour 且 price >= discharge floor：negative discharging intent；
- 其他情况：zero idle intent。

小时使用 context timestamp 自带时区中的 0～23 本地 hour，不做时区转换。价格是
literal signed finite CNY/kWh；功率是 literal non-negative kW magnitude。所有阈值
比较包含等号。

**职责分离：**

Capability 只表达基于时间和电价的业务偏好。它不检查 SOC、reserve SOC、电池功率
能力、Grid import/export limit、PCS/BMS 或 device availability。物理可行性仍由
Constraint 层处理，Evaluation flow 保持不变。

**新增文件：**

- `capability/tou.py`；
- `tests/unit/capability/test_tou.py`；
- `tasks/TASK-046.md`；
- `architecture/adr/ADR-045-tou-energy-capability.md`。

**验证内容：**

- low-price charge、high-price discharge 与 idle；
- inclusive price thresholds；
- hour tuple 类型、范围、唯一性与 non-overlap；
- signed finite raw CNY/kWh；
- non-negative raw kW intent magnitudes；
- parameters/capability frozen、slotted、无 `__dict__`；
- exact parameter identity 与 context 不变；
- 无 Constraint、Integration、Runtime、Dispatch、Device 反向依赖；
- Policy、Intent、Legacy contracts 保持不变；
- public imports。

**关键设计决策：**

Tariff/time facts 通过 immutable parameters 构造注入，保持
`EMSCapabilityBoundary.evaluate(context)` 不变。TASK-046 不读取 tariff database、
system clock 或 future forecast，不实现 optimizer、SOC/功率/Grid Constraint、
runtime、dispatch、PCS/BMS、device command、cache 或 history。

## TASK-047 EMS Capability Composition Boundary

**目标：**

建立多个 EMS Capability 的抽象、确定性组合合同。

**实现内容：**

- 新增 abstract、empty-slotted `CapabilityCompositionBoundary`；
- 定义 `evaluate(context, capabilities) -> tuple[DecisionIntent, ...]`；
- 固定 caller tuple order；
- 固定每个 capability tuple position exactly once；
- 固定 exact context 与 exact returned intent identity；
- 固定 repeated positions 不自动 deduplicate；
- 固定异常立即停止并原样传播；
- 不新增 concrete production composition implementation；
- 通过顶层 `capability` package 提供公开导入。

**架构意义：**

```text
DecisionContext
        +
caller-ordered tuple[EMSCapabilityBoundary, ...]
        |
        v
CapabilityCompositionBoundary
        |
        v
tuple[DecisionIntent, ...]
```

TASK-047 只建立 composition seam，不决定多个业务目标中谁获胜。它让未来 resolution
可以消费有序、exact、只执行一次的 capability artifacts，而不用重新执行 Capability。

**Ordering 与 Identity：**

- caller tuple 位置是唯一权威顺序；
- 不排序、不选择、不去重；
- 每个位置接收 exact DecisionContext；
- 每个位置执行 exactly once；
- 输出 tuple 与输入 tuple 一一对应；
- 每个输出保持 Capability 返回的 exact DecisionIntent reference；
- empty capability tuple 对应 empty intent tuple。

**Resolution exclusion：**

Boundary 不选择 winner，不按 capability class 排序，不相加、平均、裁剪或 normalize
battery power，不生成 fallback，也不执行评分、优先级或 conflict resolution。TASK-047
不返回单个 resolved intent。

**新增文件：**

- `capability/composition.py`；
- `tests/unit/capability/test_composition.py`；
- `tasks/TASK-047.md`；
- `architecture/adr/ADR-046-capability-composition-boundary.md`。

**验证内容：**

- abstract boundary 与 exact signature；
- caller order 和 exactly-once；
- repeated positions 不去重；
- exact context/intent identity；
- empty tuple；
- exception propagation 与 later-call prevention；
- empty slots、无 `__dict__`、cache 或 history；
- production package 无 concrete composition；
- 无 TOU/Constraint/Integration/Runtime/Device dependency；
- Intent、Constraint、Evaluation、Legacy contracts 保持不变；
- public import。

**关键设计决策：**

返回 ordered intent tuple，而不是单个 intent，避免在 boundary task 中暗中加入 selection、
priority、scoring、optimization 或 business conflict rules。具体 composition
implementation 和 intent resolution 均需要未来独立 review。本任务不实现 TOU、
SOC、Grid、PCS/BMS、runtime、forecast、optimization、dispatch、device control、
persistence、cache 或 history。

## TASK-048 Intent Resolution Boundary

**目标：**

建立多个 capability candidate intents 进入单一 resolved `DecisionIntent` 的抽象扩展
入口，但不实现任何 resolution 或 arbitration 算法。

**实现内容：**

- 新增 abstract、empty-slotted `IntentResolutionBoundary`；
- 定义
  `resolve(candidates: tuple[DecisionIntent, ...]) -> DecisionIntent`；
- 使用 immutable tuple 表达既有 candidate artifacts；
- 不重新执行 Capability；
- 不修改或保存 candidates；
- 不新增 concrete production resolver；
- 通过顶层 `capability` package 提供公开导入。

**架构意义：**

```text
CapabilityCompositionBoundary
        |
        v
tuple[DecisionIntent, ...]
        |
        v
IntentResolutionBoundary
        |
        v
DecisionIntent
        |
        v
Constraint Layer
```

TASK-048 把“确定性地产生多个独立 capability 输出”与“未来根据业务规则得到一个
source intent”分成两个边界。Constraint 继续只处理物理可行性，不负责选择业务目标。

**Boundary-only contract：**

- 输入为 immutable candidate tuple；
- 输出类型为一个 immutable `DecisionIntent`；
- boundary 本身不实现 priority、weight、score 或 ranking；
- 不自动选择 candidate；
- 不相加、平均、裁剪或 merge intent；
- 不实现 optimization、fallback 或 AI selection；
- empty、single、conflicting candidates 的行为留给未来具体 resolver task；
- resolved identity 与错误合同也由未来实现明确。

**新增文件：**

- `capability/resolution.py`；
- `tests/unit/capability/test_resolution.py`；
- `tasks/TASK-048.md`；
- `architecture/adr/ADR-047-intent-resolution-boundary.md`。

**验证内容：**

- abstract boundary 与 exact signature；
- tuple candidate input 与 `DecisionIntent` output annotation；
- test-only single candidate exact identity；
- empty slots、无 `__dict__`、cache、history 或 runtime state；
- production package 无 concrete resolver；
- 无 Constraint、Evaluation、Runtime、Dispatch、Device dependency；
- Intent、Capability、Constraint、Evaluation 与 Legacy contracts 保持不变；
- public import。

**关键设计决策：**

Resolution 独立于 Composition 与 Constraint。TASK-048 只为未来 business-resolution
策略保留明确 seam，不声明 tuple 顺序就是 priority，也不规定返回现有 candidate 或
构造新 intent。本任务不实现 TOU、SOC、Grid、PCS/BMS、runtime、forecast、
optimization、dispatch、device control、persistence、cache 或 history。

## TASK-049 Self Consumption Capability

**目标：**

实现第二个具体 EMS Capability，根据当前 PV 与 Load 事实生成 self-consumption
`DecisionIntent` candidate。

**实现内容：**

- 新增 fieldless、empty-slotted `SelfConsumptionCapability`；
- 继承稳定的 `EMSCapabilityBoundary`；
- 定义 `evaluate(DecisionContext) -> DecisionIntent`；
- 只读取 `pv_power_kw` 与 `load_power_kw`；
- 使用 raw kW 公式 `pv_power_kw - load_power_kw`；
- PV surplus 产生正值 charge intent；
- PV deficit 产生负值 discharge intent；
- balanced 产生 zero idle intent；
- 通过顶层 `capability` package 提供公开导入。

**架构意义：**

```text
DecisionContext
        |
        v
SelfConsumptionCapability
        |
        v
DecisionIntent candidate
        |
        v
Future Composition / Resolution
        |
        v
Constraint Layer
```

TASK-049 证明 TOU 与 Self Consumption 等不同业务能力可以在相同 Capability contract
下独立产生候选意图。它不让 Capability 互相感知，也不提前执行 resolution。

**Physical contract：**

- PV 与 Load 都是 literal、unscaled kW；
- `battery_power_intent_kw = PV - Load`；
- 正值表示充电意图；
- 负值表示放电意图；
- 零表示空闲意图；
- 无 conversion、scaling、clipping、saturation 或 rounding。

**Policy / Constraint separation：**

TASK-037 的 `SelfConsumptionPolicy` 保持独立并返回 `DecisionContextResult`。
TASK-049 的 `SelfConsumptionCapability` 直接返回 `DecisionIntent`。两者无 inheritance、
adapter、call、migration 或 shared mutable state。

Capability 不读取或执行 SOC、reserve SOC、battery power limit、Grid/export limit 或
zero-export。完整 PV-load imbalance 作为候选意图输出，物理可行性继续由 Constraint
负责。

**新增文件：**

- `capability/self_consumption.py`；
- `tests/unit/capability/test_self_consumption.py`；
- `tasks/TASK-049.md`；
- `architecture/adr/ADR-048-self-consumption-capability.md`。

**验证内容：**

- Capability boundary inheritance 与 exact signature；
- surplus、deficit 与 balanced cases；
- raw kW 符号语义；
- 不执行 SOC/battery limit；
- Grid、price、export facts 不影响输出；
- context 不变；
- fieldless slots、无 `__dict__`、cache 或 history；
- Policy independence；
- 无 Constraint、Evaluation、Runtime、Dispatch、Device dependency；
- Intent、Capability Boundary、Constraint、Evaluation 与 Legacy contracts 保持不变；
- public import。

**关键设计决策：**

实现直接表达 `PV - Load`，不调用已有 `SelfConsumptionPolicy`，保持 Capability 与
Policy 两条已接受 extension contract 独立。本任务不实现 SOC、Battery/Grid limit、
zero-export、TOU、optimization、forecast、runtime、dispatch、PCS/BMS、device
control、persistence、cache 或 history。

## TASK-050 Deterministic Intent Resolution Implementation

**目标：**

实现第一个 concrete、replaceable Intent Resolver，使用 caller 显式注入的 immutable
规则把 candidate tuple 解析为一个 `DecisionIntent`。

**实现内容：**

- 新增 frozen/slotted `DeterministicIntentResolutionParameters`；
- 参数只包含 required `selected_candidate_index`；
- index 是 unitless、zero-based、non-negative integer；
- 新增 frozen/slotted `DeterministicIntentResolutionImplementation`；
- 继承并保持 `IntentResolutionBoundary.resolve(candidates)`；
- 校验 tuple、全部 candidate 类型和 index range；
- 返回指定 tuple position 的 exact `DecisionIntent`；
- 保持 exact immutable parameter identity；
- 通过顶层 `capability` package 提供公开导入。

**架构意义：**

```text
tuple[DecisionIntent, ...]
        +
immutable selected_candidate_index
        |
        v
DeterministicIntentResolutionImplementation
        |
        v
exact selected DecisionIntent
        |
        v
Constraint Layer
```

TASK-050 证明 Resolution Boundary 可以被具体实现替换，同时不让 Resolver 知道 TOU、
Self Consumption 或未来 capability 名称。

**Explicit rule：**

- candidate 顺序由 caller 提供；
- selected index 由 caller 通过 immutable parameters 提供；
- 没有默认 index；
- 不隐式选择 first/last；
- 不从 capability name、type 或 intent value 推断 priority；
- 同样的 parameters 与 candidate tuple 返回同一个 exact candidate reference。

**Identity 与 Validation：**

```python
resolved is candidates[selected_candidate_index]
```

Resolver 不 copy、reconstruct、serialize、sort、deduplicate、sum、average、clip 或
normalize intents。错误 container/element 类型抛出 `TypeError`；错误 index 参数或
不存在的位置抛出 `ValueError`，错误消息包含字段名。

**新增文件：**

- `capability/deterministic_resolution.py`；
- `tests/unit/capability/test_deterministic_resolution.py`；
- `tasks/TASK-050.md`；
- `architecture/adr/ADR-049-deterministic-intent-resolution.md`。

**验证内容：**

- unchanged boundary inheritance 与 exact signature；
- 多个 index 的 deterministic selection；
- exact candidate identity；
- tuple order 与 repeated positions；
- index type、non-negative 与 range validation；
- candidate tuple/element validation；
- parameters/implementation frozen、slotted、无 `__dict__`；
- exact parameter identity；
- 无 cache、history 或 runtime state；
- 无 capability name、TOU/Self Consumption special case；
- 无 Constraint、Evaluation、Runtime、Dispatch、Device dependency；
- Intent、Boundary、Capability、Constraint、Evaluation 与 Legacy contracts 保持不变；
- public import。

**关键设计决策：**

选择规则必须公开存在于 required immutable parameters，而不是隐藏在 resolver control
flow 中。TASK-050 使用最小的 zero-based index configuration，不添加 priority table、
weight、score、ranking、intent arithmetic、optimization 或 forecast。本任务不处理
SOC、Battery/Grid limit、zero-export、Constraint/Evaluation execution、runtime、
dispatch、PCS/BMS、device control、persistence、cache 或 history。

## TASK-051 Phase 3 Decision Flow Integration Validation

**目标：**

使用现有生产组件验证完整 Phase 3 decision flow，不新增算法或生产边界。

**实现内容：**

- 新增 `tests/integration/test_phase3_decision_flow.py`；
- 使用现有 `SelfConsumptionCapability` 与 `TOUEnergyCapability`；
- 通过 test-only composition 按 caller order exactly once 执行两个 Capability；
- 使用现有 `DeterministicIntentResolutionImplementation` 显式选择 candidate；
- 使用现有 Battery 与 Grid Constraint 和 `ConstraintEvaluationPipeline`；
- 从 exact stage artifacts 构建 `ConstraintExplanationChain`；
- 从 exact result、source/feasible intent 和 explanation 构建
  `DecisionEvaluationCycle`；
- 使用 test-only probes 记录调用次数和 exact object references。

**架构意义：**

```text
Capability
        |
        v
Capability Composition
        |
        v
Intent Resolution
        |
        v
DecisionIntent
        |
        v
Constraint Pipeline
        |
        v
Constraint Explanation Chain
        |
        v
Decision Evaluation Cycle
```

TASK-051 是 Phase 3 的 integration checkpoint。它证明已接受的独立边界可以形成完整
决策链，同时继续保持 Capability、Resolution、Constraint、Explanation 与 Cycle 的
职责分离。

**场景：**

- PV surplus：Self Consumption candidate 为正值充电意图，Battery Constraint 限制
  充电功率，Grid Constraint 接收前一阶段 exact feasible intent；
- PV deficit：Self Consumption candidate 为负值放电意图，Battery Constraint 创建
  新 immutable intent，后续 Grid、Explanation 和 Cycle 保持 exact lineage。

**Identity 与 execution 验证：**

- composition candidates 保持 Capability 返回 identity；
- resolved intent 是 caller index 对应的 exact candidate；
- `DecisionContextResult.intent` 与 Cycle `source_intent` 保持 exact identity；
- 每个 Constraint 接收上一阶段 exact feasible inner intent；
- Explanation Entry、Chain 和 Cycle 保存 exact artifacts；
- 每个 Capability exactly once；
- 每个 Constraint exactly once；
- Explanation 和 Cycle 构建不触发重复执行。

**新增文件：**

- `tests/integration/test_phase3_decision_flow.py`；
- `tasks/TASK-051.md`。

**关键设计决策：**

只增加 integration validation。顺序 composition 和调用 probes 仅存在于测试文件，
用于验证既有抽象合同，不成为生产 Capability、Resolver、Constraint 或 orchestration
实现。本任务不修改 `DecisionIntent`、Policy、Evaluation、Runtime、Legacy 或任何
现有生产合同，也不增加 optimization、forecast、dispatch 或 device control。

## TASK-052 Phase 3 EMS Capability Layer Completion Review

**目标：**

完成 TASK-045～051 的正式架构冻结审查，确认 EMS Capability Layer 可以作为稳定基线
进入后续阶段。

**审查内容：**

- Capability Boundary、TOU Capability 与 Self Consumption Capability；
- caller-owned Composition 与 explicit Resolution；
- source/feasible intent lineage；
- Battery 与 Grid Constraint 职责；
- Explanation Chain 与 DecisionEvaluationCycle evidence-only 行为；
- TASK-051 end-to-end exactly-once evidence；
- capability-to-contract dependency direction；
- legacy EMSPolicy、DecisionResult、Runtime 与 Execution isolation；
- TASK、ADR 和长期文档一致性。

**审查结论：**

Phase 3：PASS。

```text
DecisionContext
        |
        v
EMS Capability candidates
        |
        v
Composition
        |
        v
Explicit Resolution
        |
        v
source DecisionIntent
        |
        v
Constraint Pipeline
        |
        v
FeasibleDecisionIntent
        |
        v
Explanation Chain
        |
        v
DecisionEvaluationCycle
```

**Identity 与 execution：**

- resolved intent 是 caller index 选择的 exact candidate；
- Cycle source intent 是 exact `DecisionContextResult.intent`；
- 下一 Constraint 输入是上一阶段 exact feasible inner intent；
- Chain 与 Cycle 保存 exact final feasible wrapper；
- Capability 与 Constraint exactly once；
- Explanation 与 Cycle 不重新执行 Capability 或 Constraint。

**Dependency 与 Legacy：**

- `capability -> kernel decision contracts`；
- kernel 不依赖 capability implementation；
- Phase 3 未修改 legacy `EMSPolicy`、legacy `DecisionResult`、Runtime 或 Execution。

**文档一致性修正：**

发现 `EOS_架构说明.md` 的开头仍写“截至 TASK-037”，但正文已经覆盖 TASK-051。
TASK-052 将范围更新为 TASK-052，并明确 Phase 3 为 TASK-045～052、状态 Completed。
该修正仅涉及文档，没有生产代码或测试变更。

**新增文件：**

- `tasks/TASK-052.md`；
- `architecture/adr/ADR-050-phase3-completion-review.md`。

**验证结果：**

- pytest：918 passed；
- Ruff check：passed；
- Ruff format：passed；
- mypy：passed。

**关键设计决策：**

冻结的是边界、依赖方向和 identity invariants，不是禁止未来增加 Capability。任何未来
合同修改、legacy migration、Runtime/Device integration 或新的 resolution strategy
都必须进入独立 TASK 与架构审查，不能隐藏在具体 Capability 中。

## TASK-053 EMS Objective Boundary

**目标：**

建立独立 Objective Description Layer，只描述 EMS 关注什么，不决定电池应该做什么。

**实现内容：**

- 新增 abstract、stateless `EMSObjectiveBoundary`；
- 新增 frozen/slotted `ObjectiveDescriptor`；
- 新增 frozen/slotted `ObjectiveCollection`；
- 公开 API 只导出上述三个合同；
- 将独立 `objective` package 纳入构建与 coverage 配置。

**架构意义：**

```text
EMSObjectiveBoundary
        |
        v
ObjectiveCollection
        |
        v
ObjectiveDescriptor tuple
```

Objective 与 Capability 的职责不同：Objective 描述关注事项，Capability 才可能在未来
根据事实产生意图。TASK-053 不连接两层，也不新增任何 concrete objective。

**不可变与身份：**

- descriptor 和 collection 均 frozen/slotted；
- collection 只接受 tuple；
- 保留 caller-supplied tuple 与 descriptor exact identity；
- boundary 使用 empty slots，无 instance state、cache 或 history。

**新增文件：**

- `objective/__init__.py`；
- `objective/base.py`；
- `objective/model.py`；
- `tests/unit/objective/`；
- `tasks/TASK-053.md`；
- `architecture/adr/ADR-051-ems-objective-boundary.md`。

**关键设计决策：**

不增加 concrete objectives、priority、weight、score、optimization、resolver 或 intent
generation。Objective 不能读取或修改 Kernel、Capability、Constraint、Evaluation、
Runtime 或 legacy 路径，也不能决定充电、放电或空闲。

**验证结果：**

- pytest：936 passed；
- Ruff check：passed；
- Ruff format：passed；
- mypy：passed。

## TASK-054 Objective Activation Boundary

**目标：**

在独立 Objective Layer 中建立最小 activation seam，表达哪些已描述 Objective 处于
active 集合，同时保持 Objective 不决定电池行为。

**实现内容：**

- 新增 abstract、stateless `ObjectiveActivationBoundary`；
- 新增 frozen/slotted `ActiveObjectiveCollection`；
- 更新 objective public API；
- 增加 identity、immutability、exactly-once 和 dependency isolation 单元测试。

**架构意义：**

```text
ObjectiveCollection
        |
        v
ObjectiveActivationBoundary
        |
        v
ActiveObjectiveCollection
```

Description 与 Activation 被明确分离：前者说明 EMS 关注事项，后者只记录哪些 exact
descriptors 处于 active 集合。两者都不产生策略、意图或设备行为。

**Identity 与 exactly once：**

- `active.source_collection` 是 exact input collection；
- `active.active_objectives` 是 exact caller tuple；
- 每个 active descriptor 必须以 `is` 关系来自 source；
- equal-but-reconstructed descriptor 被拒绝；
- 一次调用产生一个 result，不调用 `describe()` 或其他 EOS layer。

**新增文件：**

- `objective/activation.py`；
- `tests/unit/objective/test_activation.py`；
- `tasks/TASK-054.md`；
- `architecture/adr/ADR-052-objective-activation-boundary.md`。

**关键设计决策：**

不增加 concrete activation、objective priority、ranking、conflict resolution、weight、
score、optimization、resolver 或 intent generation。不修改 Kernel、DecisionContext、
Capability、Constraint、Evaluation、Runtime 或 legacy 路径。

**验证结果：**

- pytest：948 passed；
- Ruff check：passed；
- Ruff format：passed；
- mypy：passed。

## TASK-055 Objective-Capability Mapping Boundary

**目标：**

在 Phase 4 Objective Layer 中建立 Objective 与 Capability descriptor 的 immutable
mapping seam，只表达支撑关系，不实现决策逻辑。

**实现内容：**

- 新增 frozen/slotted `CapabilityDescriptor` contract；
- 新增 frozen/slotted `ObjectiveCapabilityMapping`；
- 新增 frozen/slotted `ObjectiveCapabilityMappingCollection`；
- 新增 abstract、stateless `ObjectiveCapabilityMappingBoundary`；
- 更新 Objective 与 Capability public API；
- 增加 identity、immutability、empty/multiple mapping 与 dependency direction 测试。

**架构意义：**

```text
ObjectiveCollection / ActiveObjectiveCollection
        |
        v
ObjectiveCapabilityMappingBoundary
        |
        v
ObjectiveCapabilityMappingCollection
        |
        v
ObjectiveDescriptor -> tuple[CapabilityDescriptor, ...]
```

Mapping output 停留在 descriptor 层，不保存、构造或执行 Capability implementation。

**Identity 与 dependency：**

- mapping 保存 exact Objective 与 Capability descriptors；
- collection 保存 exact source 与 mappings tuple；
- equal-but-reconstructed Objective 被拒绝；
- `objective.mapping -> capability.descriptor`；
- Capability package 不依赖 Objective。

**新增文件：**

- `capability/descriptor.py`；
- `objective/mapping.py`；
- `tests/unit/capability/test_descriptor.py`；
- `tests/unit/objective/test_mapping.py`；
- `tasks/TASK-055.md`；
- `architecture/adr/ADR-053-objective-capability-mapping-boundary.md`。

**关键设计决策：**

不增加 concrete mapping、Capability instance/class/factory、selection、ranking、priority、
score、weight、optimization、execution、resolver 或 intent generation。不修改 Kernel、
DecisionContext、DecisionIntent、Constraint、Evaluation、Runtime、Execution 或 legacy。

**验证结果：**

- pytest：971 passed；
- Ruff check：passed；
- Ruff format：passed；
- mypy：passed。

## TASK-056 Capability Discovery Boundary

**目标：**

建立 descriptor-only Capability Discovery 抽象边界，以不可变集合报告可用的
`CapabilityDescriptor` references，不引入设备或行为发现。

**实现内容：**

- 新增 frozen/slotted `AvailableCapabilityCollection`；
- 新增 abstract、stateless `CapabilityDiscoveryBoundary`；
- 更新 Capability public API；
- 增加 tuple/descriptor identity、immutability、empty collection、dependency isolation
  和无 concrete production implementation 测试。

**架构意义：**

```text
CapabilityDiscoveryBoundary
        |
        v
AvailableCapabilityCollection
        |
        v
tuple[CapabilityDescriptor, ...]
```

Discovery 只报告 descriptor availability。它不把 Capability implementation、设备访问、
协议扫描、matching、selection、activation 或 intent generation 带入稳定契约。

**Identity 与 dependency：**

- collection 保存 exact caller/provider descriptor tuple；
- tuple order 与每个 descriptor identity 原样保持；
- `capability.discovery -> capability.descriptor`；
- 不依赖 Objective、Kernel、Constraint、Evaluation、Runtime、Execution 或 Device。

**新增文件：**

- `capability/discovery.py`；
- `tests/unit/capability/test_discovery.py`；
- `tasks/TASK-056.md`；
- `architecture/adr/ADR-054-capability-discovery-boundary.md`。

**关键设计决策：**

不增加 concrete discovery provider、Capability instance/class/factory、device connection、
CAN/Modbus、matching、selection、ranking、priority、activation、optimization、resolver 或
`DecisionIntent` generation。不修改既有 Capability behavior、Objective mapping、Constraint、
Evaluation、Runtime、Execution 或 legacy。

**验证结果：**

- pytest：981 passed；
- Ruff check：passed；
- Ruff format：passed；
- mypy：passed；
- pre-commit：passed。

## TASK-057 Capability Matching Boundary

**目标：**

建立 Required Capability 与 Available Capability descriptors 的 immutable matching seam，
只表达关系事实，不实现匹配、仲裁或执行算法。

**实现内容：**

- 新增 frozen/slotted `RequiredCapabilityCollection`；
- 新增 frozen/slotted `CapabilityMatch`；
- 新增 frozen/slotted `CapabilityMatchCollection`，包含 immutable
  `missing_required: tuple[CapabilityDescriptor, ...]`；
- 新增 abstract、stateless `CapabilityMatchingBoundary`；
- 更新 Capability public API；
- 增加 all matched、partially matched、fully missing、source/descriptor/match/missing
  identity、互斥完备性、immutability、empty collection、dependency isolation 与无
  concrete production implementation 测试。

**架构意义：**

```text
RequiredCapabilityCollection
        |                         AvailableCapabilityCollection
        +-------------------------+
                                  |
                                  v
                    CapabilityMatchingBoundary
                                  |
                                  v
                    CapabilityMatchCollection
```

Matching output 停留在 descriptor relationship 层，不包含 Capability implementation、
设备事实、选择结果、激活状态或电池意图。

**Identity 与 dependency：**

- required/available source collections 保持 exact identity；
- match 保存 exact required 与 available descriptors；
- matches tuple、caller order 与 match identities 原样保持；
- missing-required tuple 与 descriptor identities 原样保持；
- 每个 required descriptor 必须且只能属于 matched 或 missing 类别；
- `capability.matching` 只依赖 descriptor 与 discovery contracts；
- 不依赖 Objective、Kernel、Constraint、Evaluation、Runtime、Execution 或 Device。

**新增文件：**

- `capability/matching.py`；
- `tests/unit/capability/test_matching.py`；
- `tasks/TASK-057.md`；
- `architecture/adr/ADR-055-capability-matching-boundary.md`。

**关键设计决策：**

不增加 concrete matching algorithm、Capability instance、device/CAN/Modbus dependency、
ranking、scoring、priority、selection、optimization、fallback、activation、resolver 或
`DecisionIntent` generation。不修改 Discovery、Objective mapping、Constraint、Evaluation、
Runtime、Execution 或 legacy。

**验证结果：**

- pytest：999 passed；
- Ruff check：passed；
- Ruff format：passed；
- mypy：passed；
- pre-commit：passed。

## TASK-058 Capability Activation Boundary

**目标：**

在已完成的 Capability matching facts 之上建立 immutable activation seam，只表达 exact
matched available descriptors 的 active/inactive 状态。

**实现内容：**

- 新增 frozen/slotted `ActiveCapabilityCollection`；
- 新增 abstract、stateless `CapabilityActivationBoundary`；
- active/inactive 使用 tuple-only descriptor references；
- 每个 matched descriptor 必须且只能属于一个状态类别；
- 更新 Capability public API；
- 增加 exactly-once、identity、完整状态覆盖、immutability、dependency isolation 与无
  concrete production implementation 测试。

**架构意义：**

```text
CapabilityMatchCollection
        |
        v
CapabilityActivationBoundary
        |
        v
ActiveCapabilityCollection
        |-- active_capabilities
        `-- inactive_capabilities
```

Matching 继续只保存 relationship facts；Activation 独立保存后续 descriptor status，二者不
混合，也不连接 executable Capability、Decision、Constraint、Runtime 或 Device。

**Identity 与 dependency：**

- source match collection 保持 exact identity；
- active/inactive tuples、caller order 与 descriptor identities 原样保持；
- equal-but-reconstructed 或 unrelated descriptor 被拒绝；
- `capability.activation` 只依赖 descriptor 与 matching contracts；
- 不依赖 Objective、Kernel、Constraint、Evaluation、Runtime、Execution 或 Device。

**新增文件：**

- `capability/activation.py`；
- `tests/unit/capability/test_activation.py`；
- `tasks/TASK-058.md`；
- `architecture/adr/ADR-056-capability-activation-boundary.md`。

**关键设计决策：**

不增加 concrete activation algorithm、Capability instance、priority、ranking、scoring、
selection、optimization、conflict resolution、fallback、`DecisionIntent` generation、
Constraint、Device/CAN/Modbus dependency、Runtime 或 persistence。

**验证结果：**

- pytest：1012 passed；
- Ruff check：passed；
- Ruff format：passed；
- mypy：passed；
- pre-commit：passed。

## TASK-059 Objective-Capability Activation Composition

**目标：**

建立 Objective 与完整 `ActiveCapabilityCollection` 之间的 immutable composition seam，只
表达该 Objective 使用哪些已经 active 的 capability descriptors。

**实现内容：**

- 新增 frozen/slotted `ObjectiveCapabilityActivationComposition`；
- 新增 abstract、stateless
  `ObjectiveCapabilityActivationCompositionBoundary`；
- composition 直接保存 exact Objective 与 exact Active Capability Collection；
- 完整保留 nested active tuple，拒绝重复 descriptor identity；
- 更新 Objective public API；
- 增加 objective/capability identity、completeness、duplicate rejection、reconstructed
  descriptor rejection、immutability、dependency isolation 与无 concrete production
  implementation 测试。

**架构意义：**

```text
ObjectiveDescriptor             ActiveCapabilityCollection
        |                                  |
        +----------------------------------+
                                           |
                                           v
          ObjectiveCapabilityActivationCompositionBoundary
                                           |
                                           v
             ObjectiveCapabilityActivationComposition
```

Composition 不定义第二个 capability subset，因此不会隐式选择或遗漏 active descriptors。
Objective package 只依赖稳定 Capability contract；Capability package 不反向依赖 Objective。

**Identity 与 dependency：**

- Objective 与 Active Capability Collection 保持 exact identity；
- nested active tuple、caller order 与 descriptor identities 原样保持；
- duplicate active descriptor identity 被拒绝；
- reconstructed capability descriptor 无法进入有效 active source；
- `objective.activation_composition` 只依赖 objective model 与 capability activation contract；
- 不依赖 Constraint、Evaluation、Runtime、Execution 或 Device。

**新增文件：**

- `objective/activation_composition.py`；
- `tests/unit/objective/test_activation_composition.py`；
- `tasks/TASK-059.md`；
- `architecture/adr/ADR-057-objective-capability-activation-composition.md`。

**关键设计决策：**

不增加 capability subset、selection、ranking、priority、scoring、optimization、conflict
resolution、fallback、activation logic、Capability execution、`DecisionIntent` generation、
Constraint、Runtime、Device 或 persistence。

**验证结果：**

- pytest：1027 passed；
- Ruff check：passed；
- Ruff format：passed；
- mypy：passed；
- pre-commit：passed。

## Phase 4 Objective & Capability Architecture 回顾

### TASK-053 Objective Boundary

**背景：** Decision Kernel 已能表达策略输入与输出，但缺少独立的“EMS 关注什么”描述。

**设计目的：** 将业务 Objective 从 Strategy、Intent 与 Runtime 中分离。

**核心契约：** `ObjectiveDescriptor`、`ObjectiveCollection` 与 abstract
`EMSObjectiveBoundary`；仅保存 immutable name/description descriptors。

**架构收益：** 业务目标获得稳定身份，可以独立演进并成为后续 Mapping 的 source evidence。

### TASK-054 Objective Activation Boundary

**背景：** 已描述 Objective 不等于当前 active Objective，需要独立状态边界。

**设计目的：** 表达 exact source objectives 的 active 集合，而不引入优先级或冲突处理。

**核心契约：** `ObjectiveActivationBoundary` 接收 `ObjectiveCollection`，返回保存 exact source
与 descriptor tuple 的 `ActiveObjectiveCollection`。

**架构收益：** Objective description 与 activation 生命周期分离，identity lineage 可验证。

### TASK-055 Objective-Capability Mapping

**背景：** Objective 需要描述可由哪些业务能力支撑，但不能依赖 Capability implementation。

**设计目的：** 在 descriptor 层表达 Objective-to-Capability support relationships。

**核心契约：** immutable `ObjectiveCapabilityMapping`、mapping collection 与 abstract mapping
boundary；输出只包含 `CapabilityDescriptor`。

**架构收益：** 依赖方向保持 `objective -> capability contracts`，Capability package 不反向依赖
Objective，也没有 selection、ranking 或 intent generation。

### TASK-056 Capability Discovery

**背景：** Mapping 描述理论支持关系，但不能说明 provider 当前报告哪些 capabilities available。

**设计目的：** 独立表达 available capability descriptor observation。

**核心契约：** abstract `CapabilityDiscoveryBoundary` 返回 immutable
`AvailableCapabilityCollection`，保持 exact tuple、order 与 descriptor identity。

**架构收益：** Availability 与设备扫描、matching、activation 和执行解耦。

### TASK-057 Capability Matching

**背景：** Required 与 Available descriptors 需要关系事实边界，同时必须显式表达未满足需求。

**设计目的：** 输出完整、不可变且 identity-based 的 matched/missing result。

**核心契约：** `RequiredCapabilityCollection`、`CapabilityMatch`、
`CapabilityMatchCollection` 与 abstract `CapabilityMatchingBoundary`。每个 required descriptor
必须且只能属于 `matches` 或 `missing_required`。

**架构收益：** Matching evidence 不再用缺席暗示 missing；后续层能够区分明确缺失与处理遗漏。

**首次审查失败与修复：** 第一版只有 `matches`。虽然当时测试全部通过，但模型无法表达
“required capability 明确 missing”，也无法区分 missing 与遗漏处理，因此正式架构审查判定
FAIL / BLOCK MERGE。修复增加：

```python
missing_required: tuple[CapabilityDescriptor, ...]
```

同时增加 complete coverage validation：每个 required descriptor 必须进入 matched 或 missing
类别之一，不能遗漏，也不能同时属于两类；missing descriptor 必须保持 source identity。新增
all matched、partially matched、fully missing、identity、omission 与 overlap tests 后重新审查通过。

该事件形成 Phase 4 的重要工程结论：

> 测试通过不等于架构完整。测试只能验证当前可表达的行为；架构审查还必须验证必要状态是否
> 都能被模型明确表达。

### TASK-058 Capability Activation

**背景：** Matched capability 不等于 Active capability，需要在 relationship facts 之后表达状态。

**设计目的：** 对 matched available descriptors 提供 active/inactive 完整互斥分类。

**核心契约：** abstract `CapabilityActivationBoundary` 接收 `CapabilityMatchCollection`，返回
frozen/slotted `ActiveCapabilityCollection`，保存 exact source 与两个 status tuples。

**架构收益：** Discovery、Matching 与 Activation 成为三个可独立审查的证据阶段；无具体
activation algorithm、Capability execution 或 Device dependency。

### TASK-059 Objective-Capability Activation Composition

**背景：** Objective 与已完成的 active Capability evidence 需要一个最终 relationship artifact。

**设计目的：** 在不选择 capability subset 的前提下保存完整 Objective-to-active-Capability
关系。

**核心契约：** frozen/slotted `ObjectiveCapabilityActivationComposition` 直接保存 exact
Objective 与 exact `ActiveCapabilityCollection`；abstract composition boundary 不提供算法。

**架构收益：** Composition completeness 由保留整个 active collection 保证；重复 capability
identity 被拒绝，selection、DecisionIntent、Runtime 与 Device 继续留在边界之外。

## TASK-061 DecisionIntent Contract

**目标：** 建立 Phase 5 Decision Formation 的最小 immutable 语义意图合同。

**实现内容：**

- 新增独立 top-level `decision_formation` package；
- 新增 frozen/slotted `DecisionIntent`；
- 定义 exact `charge`、`discharge`、`idle` action；
- 拒绝非字符串、未知值、大小写别名与空白变体；
- 新增 public import、immutability、invalid input、dependency 和 legacy isolation tests；
- 将新 package 加入 distribution 与 coverage configuration。

**架构意义：** Phase 5 获得不依赖设备功率正负方向的语义 action vocabulary，并在 Formation、
Resolution 和 Constraint 之前冻结稳定输入类型。

**核心契约：**

```text
decision_formation.DecisionIntent
└── action: charge | discharge | idle
```

Intent 只表达“希望做什么”，不是 `Command`，也不包含功率大小、设备协议、执行状态、Constraint
或 Optimization 结果。

**Legacy isolation：** 现有 `kernel.decision.DecisionIntent(battery_power_intent_kw)` 与全部
Capability、Constraint、Evaluation consumers 保持不变。Phase 5 合同没有 inheritance、adapter、
alias、conversion 或 migration。

**Identity：** TASK-061 artifact 没有引用字段，因此不声明 object-reference lineage。未来 wrapper
必须在自己的直接输入/输出合同中保持 exact Intent identity。

**新增文件：**

- `decision_formation/__init__.py`；
- `decision_formation/intent.py`；
- `tests/unit/decision_formation/`；
- `tasks/TASK-061.md`；
- `architecture/adr/ADR-059-decision-intent-contract.md`。

**关键设计决策：** Objective 不生成 Intent；`CapabilityDescriptor` 不等于 implementation；
Optimization 不等于 Decision；`DecisionIntent` 不等于 Command。TASK-061 不生成实际决策、不访问
设备状态，也不连接 Runtime、Device、PCS 或 BMS。

## TASK-065 Simulation Core Identity and Time Contracts

**背景：** Phase 6 component models 需要共享确定性的 step identity 与时间语义，但 aggregate contracts
不能早于尚未定义的 PV、Load、Tariff、Battery 和 Grid contracts。

**目标：** 只建立 immutable simulation core identity/time artifact，不提前引入 component、aggregate
state、Runtime 或 Device execution。

**实现内容：**

- 新增 frozen/slotted `SimulationStepIdentity`；
- 定义 non-negative zero-based `sequence`；
- 定义 positive finite raw `duration_seconds`；
- 要求 timestamp 为 timezone-aware datetime 或 explicit `None`；
- 保留 exact caller timestamp identity；
- 新增 focused validation、public API 和 unit tests。

**架构意义：** Simulator 获得不依赖 wall clock、UUID 或 Runtime 的确定性 step language。后续
component contracts 可以共享单位和时间语义，而无需修改 TASK-065。

**Identity：**

```text
step.timestamp is original_timestamp
```

Validation 不复制 datetime、不转换 timezone，也不生成 timestamp。

**新增文件：**

- `simulator/core.py`；
- `simulator/validation.py`；
- `tests/unit/simulator/`；
- `tasks/TASK-065.md`；
- `architecture/adr/ADR-063-simulation-core-identity-time-contracts.md`。

**关键设计决策：** TASK-065 不创建 PV、Load、Tariff、Battery、Grid、Simulation State、Scenario、
Step Input/Result、Runtime、Scheduler、Device、Command、Optimization、cache 或 history。Component
contracts 保留给 TASK-066～071，aggregate contracts 保留给 TASK-072。

## TASK-066 PV Simulation Model Contract

**背景：** Simulation core 已定义 step identity/time，但 aggregate contracts 之前需要先冻结独立 PV
component 输入、输出和 model extension seam。

**目标：** 只定义 PV simulation boundary contract，不实现 irradiance、MPPT、inverter 或其他 physics。

**实现内容：**

- 新增 frozen/slotted `PVSimulationInput`；
- 新增 frozen/slotted `PVSimulationResult`；
- 新增 abstract/stateless/empty-slotted `PVSimulationModelBoundary`；
- 输入使用 caller-supplied non-negative finite `available_power_kw`；
- 输出使用 non-negative finite `actual_power_kw`，且不超过 availability；
- 保存 exact step/input identities；
- 新增 focused validation、public API 和 unit tests。

**Identity：**

```text
simulation_input.step_identity is original_step_identity
result.simulation_input is original_simulation_input
```

**架构意义：** PV component output 具有稳定 provenance，未来具体 physics model 可以替换而不修改
aggregate contracts。Availability 是显式 simulation fact，不是预测、MPPT 结果或设备读取。

**新增文件：**

- `simulator/pv.py`；
- `tests/unit/simulator/test_pv.py`；
- `tasks/TASK-066.md`；
- `architecture/adr/ADR-064-pv-simulation-model-contract.md`。

**关键设计决策：** 不增加 concrete PV model、irradiance conversion、temperature efficiency、MPPT、
inverter、PCS、Device、Runtime、Command、aggregate State/Scenario/Step Result、Optimization、cache 或
history。

## TASK-067 Load Simulation Model Contract

**背景：** Aggregate Simulation contracts 之前需要独立冻结 Load component 的输入、输出和 extension
seam，避免把 prediction 或 user behavior 固化进基础模型。

**目标：** 只定义 Load simulation contract，不实现负载预测、profile generation、用户行为、Demand
Response 或设备读取。

**实现内容：**

- 新增 frozen/slotted `LoadSimulationInput`；
- 新增 frozen/slotted `LoadSimulationResult`；
- 新增 abstract/stateless/empty-slotted `LoadSimulationModelBoundary`；
- 输入使用 caller-supplied non-negative finite `demand_power_kw`；
- 输出使用 non-negative finite `actual_power_kw`，且不超过 demand；
- 保存 exact step/input identities；
- 新增 focused validation、public API 和 unit tests。

**Identity：**

```text
simulation_input.step_identity is original_step_identity
result.simulation_input is original_simulation_input
```

**架构意义：** Load observation 获得稳定 provenance。未来 prediction 或 behavior implementation 可
独立演进，不能污染 Simulator core、Runtime 或 aggregate contracts。

**新增文件：**

- `simulator/load.py`；
- `tests/unit/simulator/test_load.py`；
- `tasks/TASK-067.md`；
- `architecture/adr/ADR-065-load-simulation-model-contract.md`。

**关键设计决策：** 不增加 concrete Load model、forecast、profile、user behavior、Demand Response、
schedule、Device、Runtime、Command、aggregate State/Scenario/Step Result、Optimization、cache 或 history。

## TASK-068 Tariff Simulation Model Contract

**背景：** Aggregate Simulation contracts 之前需要独立冻结 Tariff component 的显式时间、价格单位、
输入、输出和 extension seam。

**目标：** 只定义 tariff simulation contract，不实现 TOU、schedule selection、price forecast、API 或
套利策略。

**实现内容：**

- 新增 frozen/slotted `TariffSimulationInput`；
- 新增 frozen/slotted `TariffSimulationResult`；
- 新增 abstract/stateless/empty-slotted `TariffSimulationModelBoundary`；
- 要求 exact step 具有 timezone-aware timestamp；
- import/export prices 使用 signed finite raw CNY/kWh；
- 保存 exact step/input identities；
- 新增 focused validation、public API 和 unit tests。

**Identity：**

```text
simulation_input.step_identity is original_step_identity
result.simulation_input is original_simulation_input
```

**架构意义：** Tariff observation 与 TOU Capability、pricing strategy、clock、external service 和
Runtime 分离。负电价场景无需修改合同即可表达。

**新增文件：**

- `simulator/tariff.py`；
- `tests/unit/simulator/test_tariff.py`；
- `tasks/TASK-068.md`；
- `architecture/adr/ADR-066-tariff-simulation-model-contract.md`。

**关键设计决策：** 不增加 concrete Tariff model、TOU、schedule、forecast、API、currency conversion、
Runtime、Device、Command、aggregate State/Scenario/Step Result、Optimization、cache 或 history。

## TASK-069 Battery Simulation Actuation Contract

**背景：** Phase 6 在定义 Battery model 前，需要先分离 feasible decision、simulation actuation 与
真实 Device Command，并补全 actuation 对 exact feasible decision 的 provenance。

**目标：** 定义最小 immutable Battery actuation artifact，不实现 Battery physics 或状态推进。

**实现内容：**

- 新增 frozen/slotted `BatterySimulationActuation`；
- 保存 exact `source_feasible_decision: FeasibleDecisionIntent`；
- 使用 signed finite raw `battery_power_kw`；
- 冻结正值充电、负值放电、零值空闲的 Simulation 符号约定；
- 拒绝 bool、非 numeric 与非 finite power；
- 新增 focused identity、immutability、dependency 和 public API tests。

**Identity：**

```text
actuation.source_feasible_decision is original_feasible_decision
```

**架构意义：** Simulation 可以证明 Battery 功率输入来自哪个 exact feasible decision，同时保持
Decision、Actuation 与 Command 三种语义分离。Kernel Decision 不依赖 Simulator。

**新增文件：**

- `simulator/battery.py`；
- `tests/unit/simulator/test_battery.py`；
- `tasks/TASK-069.md`；
- `architecture/adr/ADR-067-battery-simulation-actuation-contract.md`。

**关键设计决策：** Actuation 不计算或裁剪 power，不包含 step/state/model，不执行 SOC/SOH、效率、
退化、温度、Constraint、Optimization、Runtime、Device、Command、Dispatch、PCS/BMS、协议、cache 或
history。Battery model 保留给 TASK-070，aggregate contracts 保留给 TASK-072。

## TASK-070 Battery Simulation Model Contract

**背景：** TASK-069 已冻结 feasible decision 到 Battery actuation 的 provenance。Phase 6 还需要独立
的 Battery source-state/next-state 生命周期与 replaceable model seam。

**目标：** 定义 immutable Battery state、input、result 与 abstract model boundary，不实现 physics。

**实现内容：**

- 新增 frozen/slotted `BatterySimulationState(soc)`；
- SOC 使用 `[0, 1]` finite raw unitless fraction；
- 新增保存 exact step/source-state/actuation 的 `BatterySimulationInput`；
- 新增保存 exact input/next-state 与 signed actual power 的 `BatterySimulationResult`；
- 新增 abstract/stateless/empty-slotted `BatterySimulationModelBoundary`；
- 保持正值充电、负值放电、零值空闲的 raw kW 符号；
- 新增 focused validation、identity、public API 和 dependency tests。

**Identity：**

```text
input.step_identity is original_step
input.source_state is original_source_state
input.actuation is original_actuation
result.simulation_input is original_input
result.next_state is caller_supplied_next_state
```

**架构意义：** Battery 模拟获得明确的 immutable state transition seam。无变化可以保留 state identity，
变化则由未来 concrete model 提供新 state；artifact 自身不计算或修改状态。

**新增文件：**

- 扩展 `simulator/battery.py`；
- 扩展 `simulator/validation.py`；
- `tests/unit/simulator/test_battery_model.py`；
- `tasks/TASK-070.md`；
- `architecture/adr/ADR-068-battery-simulation-model-contract.md`。

**关键设计决策：** 不实现 SOC transition、capacity integration、efficiency、loss、degradation、SOH、
voltage、current、temperature、electrochemistry、Constraint、Optimization、Runtime、Device、Command、
Dispatch、aggregate contracts、cache 或 history。

## TASK-071 Grid Simulation Model Contract

**背景：** TASK-066～070 已建立独立 PV、Load、Tariff 与 Battery contracts。Aggregate simulation 前还需
冻结独立 Grid exchange seam，避免单一 component 提前承担系统 balance 或 Grid Constraint。

**目标：** 定义 immutable Grid input/result 与 abstract model boundary，不实现具体 Grid 行为。

**实现内容：**

- 新增 frozen/slotted `GridSimulationInput`；
- 新增 frozen/slotted `GridSimulationResult`；
- 新增 abstract/stateless/empty-slotted `GridSimulationModelBoundary`；
- requested/actual power 使用 signed finite raw kW；
- 冻结正值 import、负值 export、零值 balanced 的符号约定；
- 保存 exact step/input identities；
- 新增 focused validation、public API、dependency 和 regression tests。

**Identity：**

```text
input.step_identity is original_step
result.simulation_input is original_input
```

**架构意义：** Grid requested/actual exchange 成为独立 immutable facts。未来 aggregate layer 可以组合
component observations，而无需让 Grid contract 反向依赖 PV、Load 或 Battery。

**新增文件：**

- `simulator/grid.py`；
- `tests/unit/simulator/test_grid.py`；
- `tasks/TASK-071.md`；
- `architecture/adr/ADR-069-grid-simulation-model-contract.md`。

**关键设计决策：** 不增加 balance calculation、import/export limit、Zero Export、outage、islanding、
fault、voltage/frequency/reactive-power physics、Constraint、Optimization、Runtime、Device、Command、Dispatch、
aggregate contracts、cache 或 history。

## TASK-072 Aggregate Simulation Contract

**背景：** TASK-065～071 已完成独立 step/PV/Load/Tariff/Battery/Grid contracts。Phase 6 需要在不执行
模型的前提下，表达同一 step 的跨组件输入、结果、状态和 scenario provenance。

**目标：** 建立 immutable aggregate state/scenario/step contracts，不引入 Simulation Runtime。

**实现内容：**

- 新增 frozen/slotted `SimulationStepInput`，保存 exact step 与五类 component inputs；
- 新增 frozen/slotted `SimulationState`，保存 exact step 与五类 component results；
- 新增 frozen/slotted `SimulationStepResult`，验证 exact aggregate input/state 与每个 result/input lineage；
- 新增 frozen/slotted `SimulationScenario`，保存 caller-ordered tuple-only step inputs；
- 拒绝 value-equal 但 identity 不同的 step/input reconstruction；
- 新增 focused identity、immutability、ordering、dependency 和 public API tests。

**Identity：**

```text
component_input.step_identity is aggregate_input.step_identity
component_result.simulation_input is corresponding aggregate component input
step_result.simulation_input is original aggregate input
step_result.state is original aggregate state
scenario.steps is original caller tuple
```

**架构意义：** Phase 6 component contracts 首次形成完整 one-step evidence，并保持可验证 provenance。
Scenario 仍是 immutable description，而不是执行器或 Runtime state。

**新增文件：**

- `simulator/aggregate.py`；
- `tests/unit/simulator/test_aggregate.py`；
- `tasks/TASK-072.md`；
- `architecture/adr/ADR-070-aggregate-simulation-contract.md`。

**关键设计决策：** 不执行 component model，不排序或去重 scenario，不计算 power balance/energy、不推进
step，不增加 loop、scheduler、Runtime、Device、Command、Dispatch、Optimization、forecast、persistence、
telemetry、cache 或 history。

## TASK-073 Phase 6 Integration Validation

**背景：** TASK-065～072 已分别冻结 core、五类 component 与 aggregate contracts，需要通过完整测试证明
它们可以组合并保持 exactly-once execution 与 identity provenance。

**目标：** 仅增加 Phase 6 end-to-end integration validation，不修改 production contracts。

**实现内容：**

- 新增 test-only PV、Load、Tariff、Battery、Grid recording models；
- 验证每个 model 接收 exact component input 且执行 exactly once；
- 验证 charge/import 与 discharge/export signed-power observations；
- 验证 Battery feasible decision → actuation → input → result provenance；
- 验证 exact component results → SimulationState → SimulationStepResult lineage；
- 验证 `SimulationScenario` 保持 exact caller tuple 与 caller order；
- 验证 aggregate construction 不重新执行 component models。

**架构意义：** Phase 6 从独立 unit contracts 进入完整 integration evidence。测试证明 aggregation 是纯
observation，不是隐藏的 runner 或 Runtime。

**新增文件：**

- `tests/integration/test_phase6_simulation_flow.py`；
- `tasks/TASK-073.md`。

**关键设计决策：** 不增加 production code、concrete production model、orchestrator、balance/SOC/energy
计算、step progression、Runtime、Scheduler、Device、Command、Dispatch、persistence、cache 或 history。

## TASK-074 Phase 6 Simulation Architecture Completion Review

**背景：** TASK-065～073 已完成 core identity/time、五类 component、aggregate contracts 与 integration
validation，需要在引入任何未来模型或 runner 前冻结 Phase 6 的真实能力与非目标。

**目标：** 对 Phase 6 执行 completion review，确认 immutable、identity provenance、exactly-once evidence、
dependency direction 以及 Simulation/Runtime/Device separation。

**实现内容：**

- 审查 `SimulationStepIdentity` 的显式 sequence/duration/timestamp contract；
- 审查 PV、Load、Tariff、Battery、Grid input/result 与 abstract model boundaries；
- 审查 feasible decision → Battery actuation → Battery input/result provenance；
- 审查 aggregate input/state/result/scenario 的 exact identity contracts；
- 审查 TASK-073 exactly-once integration evidence；
- 冻结 Phase 6 contracts，并新增 Phase 6 v1.0 summary；
- 不修改 production code、tests 或 public API。

**架构意义：** EOS 获得稳定的 simulation contract platform，但不把合同完整性误写成 production simulator、
Runtime 或 Device capability。未来 physics、runner 与 progression 必须通过独立 TASK 引入。

**新增文件：**

- `tasks/TASK-074.md`；
- `architecture/adr/ADR-071-phase6-simulation-completion-review.md`；
- `docs/phase-summary/EOS_Phase6_Simulation_Architecture_v1.0.md`。

**验证结果：** Phase 6 architecture review PASS；pytest 1291 passed；Ruff lint/format passed；mypy passed；
pre-commit passed。

**关键设计决策：** 冻结 direct identity contracts；保持 Simulation != Runtime、Simulation != Device
Execution、Actuation != Command；不新增 production model、power balance、SOC transition、runner、step
progression、persistence、cache 或 history。

## TASK-075 Simulation Model Binding Contract

**背景：** Phase 6 已冻结五类 component model boundaries。未来确定性 execution 需要 caller 显式声明使用
哪些 model instances，但不能让 executor、registry 或 factory 隐式拥有模型。

**目标：** 建立 component contract 与 exact caller model reference 的 immutable binding contract。

**实现内容：**

- 新增 identity-based frozen/slotted `SimulationModelBinding`；
- 保存 exact component boundary class 与 exact caller model instance；
- 新增 identity-based frozen/slotted `SimulationModelBindingCollection`；
- 保存 exact tuple、exact binding elements 与 caller order；
- 拒绝错误 contract、contract/model mismatch、mutable collection 与错误 element；
- 使用 `eq=False` 拒绝 reconstructed equal-field binding 的 identity membership；
- 公开两个 binding contracts 并增加 focused tests。

**Identity：**

```text
binding.model is original_model
collection.bindings is original_tuple
collection.bindings[index] is original_binding
```

**架构意义：** caller ownership 与未来 execution coordination 被明确分离；后续 executor 可以消费 exact model
references，而无需引入 registry、factory、string lookup 或 hidden selection。

**新增文件：**

- `simulator/binding.py`；
- `tests/unit/simulator/test_binding.py`；
- `tasks/TASK-075.md`；
- `architecture/adr/ADR-072-simulation-model-binding-contract.md`。

**验证结果：** focused tests 22 passed；pytest 1305 passed；Ruff lint/format passed；mypy passed；
pre-commit passed。

**关键设计决策：** Binding expresses ownership/reference relationship only. It does not execute, select, create
or manage models. Collection 不排序、不去重、不补全，也不定义 exactly-once execution semantics。

## TASK-076 Single-Step Simulation Executor Boundary

**背景：** TASK-075 已表达 caller-supplied model ownership，但没有执行语义。Phase 7 需要最小单步协调器，
同时避免提前引入 scenario runner 或 Runtime。

**目标：** 使用 exact `SimulationStepInput` 与 caller bindings 执行一个确定性 simulation step，并返回既有
`SimulationStepResult`。

**实现内容：**

- 新增 stateless/empty-slotted `SingleStepSimulationExecutor`；
- 执行前验证 PV、Load、Tariff、Battery、Grid bindings 各且仅一个；
- 严格按 caller binding tuple 顺序调用；
- 每个 component model 在成功路径 exactly once；
- 每个 model 接收对应 exact component input；
- 验证 model result type，并复用 `SimulationState`/`SimulationStepResult`；
- 异常立即停止并保持 exact exception identity；
- 新增 focused execution、ordering、identity、failure 和 dependency tests。

**Identity：**

```text
step_result.simulation_input is original_step_input
state.<component>_result.simulation_input is original_component_input
bound model receives original_component_input
```

**架构意义：** EOS 首次具备单个 simulation step 的确定性 coordination，同时 executor 不拥有 model、scenario、
clock、Runtime state 或 Device execution。

**新增文件：**

- `simulator/executor.py`；
- `tests/unit/simulator/test_executor.py`；
- `tasks/TASK-076.md`；
- `architecture/adr/ADR-073-single-step-simulation-executor-boundary.md`。

**验证结果：** focused tests 24 passed；pytest 1320 passed；Ruff lint/format passed；mypy passed；
pre-commit passed。

**关键设计决策：** completeness validation 先于任何 model call；caller order 即 execution order；failure
stop-first 并原样传播；不增加 scenario loop、step progression、retry、Runtime、Device、Command 或
Optimization。

## TASK-077 Simulation Execution Trace / Evidence Contract

**背景：** TASK-076 能完成一个确定性 step，但完成后的 input、bindings、state 与 result 还缺少统一的 immutable
observation artifact。证据创建必须避免重新执行 model。

**目标：** 建立一个只保存 structurally completed single-step artifacts 的 execution trace/evidence contract。

**实现内容：**

- 新增 frozen/slotted `SimulationExecutionTrace`；
- 保存 exact simulation input、binding collection、state 与 step result；
- 验证 result → input 和 result → state 的 identity relationships；
- `create(bindings, step_result)` 只读取现有 references；
- 拒绝 mismatched identity 与 invalid types；
- 新增 observation-only、immutability、identity、dependency 和 public API tests。

**Identity：**

```text
trace.bindings is original_bindings
trace.step_result is original_step_result
trace.simulation_input is original_step_result.simulation_input
trace.state is original_step_result.state
```

**架构意义：** EOS 可以通过单一 immutable artifact 观察完成的单步结构关系，同时不会把 Trace creation 变成
execution，也不会夸大当前 contracts 对 model invocation 的证明能力。

**新增文件：**

- `simulator/trace.py`；
- `tests/unit/simulator/test_trace.py`；
- `tasks/TASK-077.md`；
- `architecture/adr/ADR-074-simulation-execution-trace-evidence-contract.md`。

**关键设计决策：** Trace 是 structurally completed evidence；不调用 executor/model，不 copy/reconstruct；
不新增 replay、progression、Runtime、Device、Command、persistence、timestamp、UUID、cache 或 history。

**验证结果：** focused tests 24 passed；pytest 1334 passed；Ruff lint/format passed；mypy passed；
pre-commit passed。

## TASK-078 Scenario Execution Boundary

**背景：** TASK-076 已提供 deterministic single-step execution，TASK-077 已提供 observation-only single-step
evidence，但 `SimulationScenario` 仍没有一个复用两者的明确执行入口。

**目标：** 按 caller 提供的 scenario step 顺序执行所有明确输入，并返回完整 immutable scenario evidence；不生成或
推进 step。

**实现内容：**

- 新增 stateless/empty-slotted `ScenarioExecutionBoundary`；
- 按 exact `scenario.steps` caller order 调用现有 single-step executor；
- 每个成功 step 恰好执行一次，每个完成 step 恰好创建一个 trace；
- 新增 frozen/slotted、tuple-only `ScenarioExecutionResult`；
- 验证 trace 数量完整且每个 trace 在相同 index 引用 exact scenario step；
- caller 重复同一个 step reference 时仍逐 occurrence 执行，并产生不同 trace identity；
- 验证每个 trace 引用 exact caller binding collection；
- 空 scenario 不调用 model；异常 stop-first 并保持 exact identity；
- 新增 ordering、exactly-once、provenance、failure、immutability、dependency 与 public API tests。

**Identity：**

```text
result.scenario is original_scenario
result.bindings is original_bindings
result.traces[index].simulation_input is original_scenario.steps[index]
result.traces[index].bindings is original_bindings
```

**架构意义：** EOS 可以执行 caller 已经完整描述的确定性 scenario，同时保持 one-step execution 与 evidence 的唯一
职责来源。Scenario execution 没有被扩展为 progression、Runtime 或 Scheduler。

**新增文件：**

- `simulator/scenario_execution.py`；
- `tests/unit/simulator/test_scenario_execution.py`；
- `tasks/TASK-078.md`；
- `architecture/adr/ADR-075-scenario-execution-boundary.md`。

**关键设计决策：** 复用 `SingleStepSimulationExecutor` 与 `SimulationExecutionTrace`，不复制其逻辑；不排序、不去重、
不生成 next step、不自动传播 state；不增加 Runtime、Scheduler、Device、Command、Dispatch、replay、persistence、
retry、cache、history、physics、Optimization 或 EMS strategy。

**验证结果：** focused tests 26 passed；pytest 1349 passed；Ruff lint/format passed；mypy passed；
pre-commit passed。

## TASK-079 Explicit Step Progression Contract

**背景：** TASK-078 可以按 caller order 执行已存在的 scenario steps，但 scenario ordering 不表达下一步输入如何与前一
步完成证据及 state transition 建立 provenance。

**目标：** 定义 previous completed evidence 与 caller-supplied next input 的 immutable、identity-based 关系，同时
保持 Simulation 不拥有 progression、time 或 lifecycle。

**实现内容：**

- 新增 `frozen=True, slots=True, eq=False` 的 `SimulationStepProgression`；
- 保存 exact previous trace、exact previous result 与 exact caller next input；
- 验证 previous result 就是 trace 中的 exact step result；
- 验证 next Battery input 的 source state 就是 previous Battery result 产生的 exact next state；
- 拒绝 value-equal reconstructed previous result 和 Battery state；
- 新增 abstract/stateless/empty-slotted `SimulationStepProgressionBoundary`；
- 不提供 concrete progression implementation；
- 新增 identity、reconstruction rejection、immutability、boundary、dependency 与 public API tests。

**Identity：**

```text
progression.previous_trace is original_trace
progression.previous_result is original_trace.step_result
progression.next_input is caller_supplied_next_input
progression.next_input.battery_input.source_state
    is progression.previous_result.state.battery_result.next_state
```

**架构意义：** Step progression 被限定为 caller-owned provenance，而不是 time scheduling、future input generation 或
Runtime lifecycle。Scenario ordering 与 step generation 继续分离。

**新增文件：**

- `simulator/progression.py`；
- `tests/unit/simulator/test_progression.py`；
- `tasks/TASK-079.md`；
- `architecture/adr/ADR-076-explicit-step-progression-contract.md`。

**关键设计决策：** 不修改 `SimulationStepInput`；不读取 clock、不推进 timestamp/sequence、不执行下一步、不保存
current step/history/runtime state；不增加 Runtime、Scheduler、Scenario runner、Replay、Persistence、Forecast、
Optimization、EMS strategy、Constraint、Command、Device 或协议。

**验证结果：** focused tests 23 passed；pytest 1360 passed；Ruff lint/format passed；mypy passed；
pre-commit passed。

## TASK-080 Phase 7 Integration Validation

**背景：** TASK-075～079 分别建立 binding、single-step execution、trace、scenario execution 与 explicit progression
contracts，需要验证组合后仍保持 deterministic execution、identity lineage、failure semantics 与隔离边界。

**目标：** 只使用 test-only models 完成 Phase 7 end-to-end validation，不新增或修改 production contract。

**验证内容：**

- `SimulationScenario -> ScenarioExecutionBoundary -> SingleStepSimulationExecutor -> SimulationExecutionTrace`；
- caller-defined step order 与 binding order；
- 每个 successful explicit step 的每个 component exactly once；
- exact scenario、bindings、steps、generated traces、states、results 与 component input/result lineage；
- exact previous trace/result、caller next input 与 Battery next-state/source-state progression lineage；
- equivalent deterministic executions 产生相同 observation values，但 evidence objects 独立；
- component failure stop-first、exact exception propagation、无 retry、无 skip、无 implicit continuation；
- failure 不返回伪造或 partial successful `ScenarioExecutionResult`；
- 无 Runtime、Scheduler、Clock、Thread、Queue、Device、Command、Optimization、Forecast 或 persistence/history。

**架构意义：** Phase 7 contracts 在不增加 production orchestration 的前提下获得完整组合证据。Simulation、Runtime、
Device Execution、step generation 与 time scheduling 的边界继续分离。

**新增文件：**

- `tests/integration/test_phase7_simulation_execution.py`；
- `tasks/TASK-080.md`；
- `architecture/adr/ADR-077-phase7-integration-validation.md`；
- `docs/phase-summary/EOS_Phase7_Deterministic_Simulation_Execution_v1.0.md`。

**关键设计决策：** test-only models 不成为 production physics；TASK-080 不修改 `simulator/`、public API 或既有 tests；
不增加 Runtime、real-time execution、scenario scheduling、automatic progression、Device control、EMS algorithm、
Optimization、persistence、history、retry 或 replay。

**验证结果：** focused integration tests 3 passed；pytest 1363 passed；Ruff lint/format passed；mypy passed；
pre-commit passed。

## TASK-081 Phase 7 Deterministic Simulation Execution Completion Review

**背景：** TASK-075～080 已完成 model binding、single-step execution、trace evidence、scenario execution、explicit
progression 与 end-to-end validation，需要在进入后续阶段前冻结 Phase 7 的保证和 non-goals。

**目标：** 以 documentation-only completion review 确认 Phase 7 架构完整性，不修改 production code、tests 或 API。

**审查结论：**

- execution 输入、model binding、step order、binding order 与 next step 均由 caller 显式提供；
- 每个 component 在每个成功 explicit step 中 exactly once；
- scenario result、trace 与 progression 保持各自直接字段的 exact identity；
- reconstructed equal-field artifact 不能替代 provenance object；
- failure stop-first，exact exception propagation，无 retry、skip、implicit continuation 或伪造成功结果；
- Simulation 不拥有 Runtime、Clock、Scheduler、Thread、Queue、loop、history 或 lifecycle；
- Phase 7 不包含 Device/Command/Dispatcher/PCS/BMS/协议，也不包含 EMS strategy、Optimization、Forecast 或决策。

**架构意义：** Phase 7 从“实现并验证”进入“完成并冻结”。后续能力必须通过新边界扩展，不能把 scenario execution 解释
成 Runtime，不能把 progression 解释成 step generation/time scheduling，也不能把 structural trace 过度描述为独立执行证明。

**新增文件：**

- `tasks/TASK-081.md`；
- `architecture/adr/ADR-078-phase7-simulation-execution-completion-review.md`。

**更新文件：** Phase 7 summary、EOS 学习手册、EOS 架构说明、TASK 演进记录。

**关键设计决策：** 只修改 Markdown；不修改 Phase 5/6 contracts、`simulator/`、public API、tests、Runtime、Device 或
execution semantics。Identity guarantee 仅覆盖每个 contract 明确验证的 direct references。

**验证结果：** `pytest`、Ruff lint/format、`mypy` 与 `pre-commit` 全部通过。

## TASK-082 24-Hour Simulation Scenario and Data Input

**背景：** Phase 7 已冻结 deterministic execution，但 EOS 仍缺少第一个 24 小时储能 Demo 可直接接收的 PV、Load、Tariff、
Battery 与初始 SOC 输入合同。

**目标：** 建立独立应用层的 immutable 24-hour data input，不提前实现 strategy、physics、runner、CSV 或 plotting。

**实现内容：**

- 新增 `BatteryParameters`，明确 capacity、charge/discharge limits、efficiency 与 reserve SOC 的单位和范围；
- 新增 `DailySimulationScenarioInput`，保存 exact 24-hour step/PV/Load/Tariff tuples、exact battery parameters 与 initial SOC；
- 验证 24 个 sequence `0..23`、3600-second duration、显式 timezone-aware consecutive timestamps；
- 拒绝 mutable list、非有限值、错误范围和非 24-hour 输入；保持 caller order，不复制、排序或补全数据。

**架构意义：** 输入数据与 executable Phase 6 `SimulationScenario` 分离。TASK-082 不伪造 Battery actuation、SOC progression 或
Grid request；未来 application runner 在事实齐备后显式装配 Phase 6 inputs，并复用 Phase 7 execution/trace。

**新增文件：**

- `ems_simulator/__init__.py`；
- `ems_simulator/input.py`；
- `tests/unit/ems_simulator/`；
- `tasks/TASK-082.md`；
- `architecture/adr/ADR-079-24h-simulation-scenario-input.md`。

**关键设计决策：** 只建立 24h scenario/data input；不修改 Phase 5～7 contracts；不增加 model execution、EMS strategy、
Battery physics、Grid balance、runner、Runtime、Device、Command、Optimization、CSV 或 plotting。

**验证结果：** focused tests、pytest、Ruff lint/format、mypy 与 pre-commit。

## TASK-083 Concrete PV Profile Simulation Model

**背景：** TASK-082 已提供 caller-owned 24h PV curve，但应用层尚无可由 Phase 7 executor 绑定和调用的 concrete PV model。

**目标：** 实现第一个 deterministic concrete component，只把 explicit hourly PV profile fact 转换为
`PVSimulationResult`。

**实现内容：**

- 新增 empty-slotted `PVProfileSimulationModel`，继承 frozen Phase 6 `PVSimulationModelBoundary`；
- 输入 exact `PVSimulationInput`，输出引用 exact input 的 immutable `PVSimulationResult`；
- `actual_power_kw` 直接等于 caller-supplied `available_power_kw`，单位为 finite non-negative raw kW；
- 支持既有 identity-based `SimulationModelBinding`；
- 覆盖正常 24h profile、zero PV、非法 power、determinism、identity、statelessness、public API 和 dependency isolation。

**架构意义：** concrete demo behavior 位于 `ems_simulator` 应用层，Phase 6/7 contracts 保持冻结。Profile 只由 TASK-082
caller input 持有，model 不保存第二份 curve，不引入 lookup、cache 或 hidden state。

**新增文件：**

- `ems_simulator/pv.py`；
- `tests/unit/ems_simulator/test_pv.py`；
- `tasks/TASK-083.md`；
- `architecture/adr/ADR-080-concrete-pv-profile-simulation-model.md`。

**关键设计决策：** 不实现 weather、irradiance、temperature、forecast、MPPT、inverter、PCS、Runtime、Device、Command、
Optimization 或 EMS strategy；不修改 Phase 5～7 contracts。

**验证结果：** focused tests、pytest、Ruff lint/format、mypy 与 pre-commit。

## TASK-084 Concrete Load Profile Simulation Model

**背景：** TASK-082 已保存 caller-owned 24h Load curve，TASK-083 已证明 concrete profile model 可以在不修改 Phase 6/7
的前提下接入 execution binding；Load component 仍缺少对应实现。

**目标：** 把 explicit hourly Load profile fact 确定性转换为 `LoadSimulationResult`。

**实现内容：**

- 新增 empty-slotted `LoadProfileSimulationModel`，继承 `LoadSimulationModelBoundary`；
- 输入 exact `LoadSimulationInput`，输出保存 exact input 的 immutable `LoadSimulationResult`；
- `actual_power_kw` 等于 caller-supplied `demand_power_kw`，单位为 finite non-negative raw kW；
- 支持现有 identity-based `SimulationModelBinding`；
- 覆盖正常 24h profile、zero Load、非法 power、determinism、identity、statelessness、public API 与 dependency isolation。

**架构意义：** application concrete Load behavior 与 frozen simulator contracts 分离。Profile 保持单一 caller ownership，
model 不持有第二份 curve，不增加 lookup、cache 或 hidden state。

**新增文件：**

- `ems_simulator/load.py`；
- `tests/unit/ems_simulator/test_load.py`；
- `tasks/TASK-084.md`；
- `architecture/adr/ADR-081-concrete-load-profile-simulation-model.md`。

**关键设计决策：** 不实现 user behavior、appliance、stochastic generation、forecast、AI、Runtime、Device、Command、
Optimization 或 EMS strategy；不修改 Phase 5～7 contracts。

**验证结果：** focused tests、pytest、Ruff lint/format、mypy 与 pre-commit。

## TASK-085 Simple Battery Physics Simulation Model

**背景：** TASK-082 提供 Battery 参数与 initial SOC，TASK-083/084 提供 concrete PV/Load profile models，但 Simulator 尚不能
根据 explicit Battery actuation 推进 SOC。

**目标：** 实现第一个 deterministic Battery physics model，计算 actual power、charge/discharge energy 和 immutable next SOC。

**实现内容：**

- 新增 frozen/slotted `SimpleBatteryPhysicsModel`，注入 exact immutable `BatteryParameters`；
- 保持 positive charging、negative discharging、zero idle 的 power contract；
- charging 使用 `P * hours * charge_efficiency`，discharging 使用 `|P| * hours / discharge_efficiency`；
- 根据 max charge/discharge power、SOC 1.0 与 reserve SOC 裁剪 actual power；
- 无状态变化时复用 exact source state，有变化时创建新 immutable state；
- result 保存 exact Battery input 及其 step/state/actuation/feasible-decision lineage；
- 覆盖 charge、discharge、idle、efficiency、power limit、SOC boundaries、duration、identity 和 determinism。

**架构意义：** EOS EMS Simulator 获得首个 physical state transition，同时 state progression 继续由 explicit input/result 驱动，
model 不持有 Runtime state。Simulation physics 保护模拟状态，不生成 EMS strategy 或新的 decision。

**新增文件：**

- `ems_simulator/battery.py`；
- `tests/unit/ems_simulator/test_battery.py`；
- `tasks/TASK-085.md`；
- `architecture/adr/ADR-082-simple-battery-physics-simulation-model.md`。

**关键设计决策：** 不修改 Phase 5～7；不实现 SOH、temperature/cell model、BMS、PCS、CAN、Runtime、Device、Command、
Optimization 或 EMS strategy。低于 reserve 的 source state 不被无能量依据地向上归一化。

**验证结果：** focused tests、pytest、Ruff lint/format、mypy 与 pre-commit。

## TASK-086 Grid Energy Balance Simulation Model

**背景：** TASK-083/084/085 已能产生 realized PV、Load 与 Battery results，Simulator 需要由这些同一步事实计算 Grid exchange。

**目标：** 实现 concrete Grid balance，同时保持现有 `GridSimulationModelBoundary` 与 Phase 5～7 contracts 不变。

**公式修正：** 冻结 Battery positive charging / negative discharging 与 Grid positive import / negative export 后，正式公式为：

```text
grid_power_kw = load_power_kw + battery_power_kw - pv_power_kw
```

旧草案 `load - battery - pv` 被拒绝，因为会让 charging 减少 import、discharging 增加 import。

**实现内容：**

- 新增 frozen/slotted、per-step `GridEnergyBalanceSimulationModel`；
- 保存 exact `PVSimulationResult`、`LoadSimulationResult`、`BatterySimulationResult` references；
- identity-validate 三个 result 与 Grid input 共享 exact step；
- 使用 realized Battery actual power 计算 finite signed raw-kW Grid exchange；
- result 保存 exact `GridSimulationInput`；
- 覆盖 PV surplus、charging、discharging、import/export/zero balance、identity、reconstructed-step rejection 与 determinism。

**架构意义：** Grid exchange 来自完成的 physical observations，而不是 Battery request。应用层获得确定性 balance，同时 frozen
Grid contract、executor 和 scenario contracts 均保持不变。

**新增文件：**

- `ems_simulator/grid.py`；
- `tests/unit/ems_simulator/test_grid.py`；
- `tasks/TASK-086.md`；
- `architecture/adr/ADR-083-grid-energy-balance-simulation-model.md`。

**关键设计决策：** future runner 显式协调 component results 后再调用 Grid model；不实现 Zero Export、Grid limit、EMS control、
PCS、inverter、Runtime、Device、Command 或 Optimization；不修改 Phase 5～7。

**验证结果：** focused tests、pytest、Ruff lint/format、mypy 与 pre-commit。

## TASK-087 24h Simulation Runner

**背景：** TASK-082～086 已提供 24 小时 caller input 与 concrete PV、Load、Battery、
Grid models，但尚无完整的连续应用执行入口。

**目标：** 使用现有 Phase 7 single-step executor 按 caller order 执行 24 个显式 step，
输出 immutable `DailySimulationResult`。

**实现内容：**

- 新增 empty-slotted `DailySimulationRunner` 与 frozen/slotted
  `DailySimulationResult`。
- 每个 step 生成 exact component inputs，并通过
  `SingleStepSimulationExecutor.execute()` exactly once。
- 使用简单 PV/Load imbalance rule 产生 Battery request；Battery physics 负责 realized
  power、efficiency、power limits 与 SOC boundaries。
- Grid 使用同一步 exact PV/Load/Battery results，按
  `Grid = Load + Battery - PV` 计算。
- 24 traces 保存 exact step evidence；23 progressions 保存 exact previous trace/result
  与 next input。
- Battery next state 作为下一 step exact source state。

**架构意义：** EOS EMS Simulator 1.0 首次具备完整 24 小时 deterministic demo flow，
同时继续保持 Simulation ≠ Runtime。连续 step 来自 caller input 和 explicit progression，
不是 clock、scheduler 或自动 lifecycle。

**新增文件：**

- `ems_simulator/runner.py`；
- `tests/unit/ems_simulator/test_runner.py`；
- `tasks/TASK-087.md`；
- `architecture/adr/ADR-084-24h-simulation-runner.md`。

**验证结果：** focused tests、full pytest、Ruff lint/format、mypy 与 pre-commit。

**关键设计决策：** 不修改 Phase 5～7 contracts；使用 frozen exact-result adapters
协调 Grid 的 same-step result dependency；不引入 Runtime、Scheduler、Clock、Device、
Command、Optimization、Forecast、MPC 或 AI；CSV、plotting 和 daily summary 留给后续任务。

## TASK-088 Simulation Result CSV Export and Visualization

**背景：** TASK-087 已生成完整 24 小时 immutable result 与 trace evidence，但尚缺少工程
可读的表格、曲线和日能量统计。

**目标：** 只读转换 `DailySimulationResult`，生成 deterministic CSV、Power/SOC SVG
和 `DailyEnergySummary`。

**实现内容：**

- 新增 stateless `SimulationResultExporter`；
- CSV 固定输出 timestamp、PV、Load、Battery、Grid power 和 SOC；
- Power SVG 展示四条 power curves，SOC SVG 展示 next-state SOC；
- Summary 计算 PV/Load energy、Battery throughput、Grid import/export energy；
- 所有 energy 由 explicit step duration 积分，单位 raw kWh；
- output artifacts 保存 exact source result identity；
- 可向 existing caller directory 写出 `simulation_result.csv`、`power_curve.svg` 和
  `soc_curve.svg`。

**架构意义：** Simulation evidence 与工程展示正式分离。Export 只观察 completed result，
不重新执行 model、runner、policy 或 constraint，也不修改 trace/state。

**新增文件：**

- `ems_simulator/output.py`；
- `tests/unit/ems_simulator/test_output.py`；
- `tasks/TASK-088.md`；
- `architecture/adr/ADR-085-simulation-result-export-visualization.md`。

**验证结果：** CSV content/order/values、SVG validity、summary energy、identity、immutability、
file output、determinism、full pytest、Ruff、mypy 与 pre-commit。

**关键设计决策：** 使用标准库 deterministic SVG，避免引入 plotting state；Grid import
和 export 分别统计；Battery throughput 使用绝对 realized power；不引入 database、dashboard、
Web API、cloud、Runtime、real-time monitoring、Device 或 Command；不修改 Phase 5～7。

## TASK-089 EOS EMS Simulator 1.0 Demo

**背景：** TASK-082～088 已分别完成输入、concrete models、24-hour runner 和工程输出，
但用户仍需要一个无需手动装配各组件的完整示例。

**目标：** 提供固定家庭光储场景与 one-command CLI，一次生成 24-step simulation、CSV、
Power/SOC curves 和 daily summary。

**实现内容：**

- 固定 24-hour PV、Load、Tariff profiles；
- 固定 10 kWh Battery parameters、initial SOC 0.50 与 reserve SOC 0.20；
- 新增 `create_demo_scenario()`、`run_demo()` 与 module CLI；
- 新增 frozen/slotted `DemoExecutionResult` 维护 exact provenance；
- 输出 `simulation_result.csv`、`power_curve.svg`、`soc_curve.svg`、
  `daily_summary.txt`；
- 增加独立 Demo guide 与 end-to-end integration tests。

**架构意义：** EOS EMS Simulator 1.0 首次成为可直接运行的应用 Demo，同时不把 simulation
变成 Runtime，不把示例 rule 变成生产 EMS strategy。

**新增文件：**

- `ems_simulator/demo.py`；
- `tests/integration/test_ems_simulator_demo.py`；
- `docs/EOS_EMS_Simulator_1.0_Demo.md`；
- `tasks/TASK-089.md`；
- `architecture/adr/ADR-086-eos-ems-simulator-1-demo.md`。

**验证结果：** scenario facts、24-step completion、output files、CLI、identity、immutability、
deterministic content、full pytest、Ruff、mypy 与 pre-commit。

**关键设计决策：** 只组合 TASK-082～088；不修改 Phase 5～8；不引入 MPC、Optimization、
AI、Forecast、Runtime、Scheduler、Device、Command、Cloud 或 real-time monitoring。

## Phase 9 EMS Strategy Architecture Freeze（TASK-090 前）

**背景：** TASK-089 已证明 EOS EMS Simulator 1.0 可以完整运行并导出工程结果，但 Demo rule
只是 simulator validation fixture，不是正式 EMS Strategy。进入实现前需要先冻结 Strategy、
Decision、Constraint 和 Simulation 的职责与 provenance。

**目标：** 通过 ADR-087 冻结独立 EMS Strategy Layer：

```text
Facts -> EMSContext -> EMSStrategyBoundary -> EMSDecision
      -> Constraint / Feasibility -> BatterySimulationActuation -> Existing Simulator
```

**文档内容：**

- `EMSContext` 是 immutable fact snapshot，保存 exact source context、objective evidence 和
  active capability information；
- `EMSStrategyBoundary.evaluate(context) -> EMSDecision` 是 abstract、stateless、exactly-one
  evaluation contract；
- `EMSDecision` 保存 exact context、strategy descriptor、semantic intent 和 requested power；
- Strategy 负责业务请求，Constraint 负责 SOC、功率、系统能力与物理可行性；
- Decision、Feasible Decision、BatterySimulationActuation 和 Command 保持独立；
- provenance 使用 direct object identity，禁止 copy、serialization reconstruction 和
  value-only lineage；
- Self Consumption、Zero Export、TOU 与 MPC 仅作为未来 Strategy implementations；
- MPC horizon 必须使用独立 caller-supplied immutable artifact，不污染基础 `EMSContext`。

**架构意义：** 正式 EMS 算法可以在不修改 Simulator physics、Phase 7 executor 或 Phase 8
Demo contracts 的前提下演进。Simulator 继续执行和验证，Strategy 只产生请求，application
composition 显式协调 feasibility 与 simulation handoff。

**修改文件：**

- `architecture/adr/ADR-087-phase9-ems-strategy-architecture.md`；
- `docs/EOS_架构说明.md`；
- `docs/EOS_学习手册.md`；
- `docs/TASK演进记录.md`。

**验证结果：** documentation-only diff review；无 production code、tests、public API 或
Phase 5～8 contract 变化。

**关键设计决策：** 本节不是 TASK-090，也不实现 Strategy。Simulator 不调用 Strategy；
Strategy 不推进 simulation step、不控制 Device、不生成 Command；未来 explicit handoff 必须
保持 direct identity provenance。

## TASK-090 EMS Core Contracts

**背景：** ADR-087 已冻结 Phase 9 EMS Strategy Layer，但正式 Strategy 需要先有稳定、不可变、
可追踪的输入和输出 artifacts。

**目标：** 实现 `EMSStrategyDescriptor`、`EMSContext` 和 `EMSDecision` 三个核心 contracts，
不实现 Strategy boundary 或算法。

**实现内容：**

- 新增独立 `ems_strategy` package 与明确 public API；
- descriptor 使用 immutable name/version identity；
- Context 保存 exact source `DecisionContext`、objective composition 和 active capability；
- capability membership 使用 `is` 验证，拒绝 value-equal reconstructed descriptor；
- Decision 保存 exact Context、Strategy descriptor 和 Phase 5 semantic Intent；
- requested power 使用 finite non-negative raw kW magnitude，并验证 action/magnitude 一致性。

**架构意义：** Strategy 输入、策略生产者身份和请求结果首次具备直接 provenance，同时继续
保持 `EMSDecision != Feasible Decision != BatterySimulationActuation != Command`。

**新增文件：**

- `ems_strategy/__init__.py`；
- `ems_strategy/descriptor.py`；
- `ems_strategy/context.py`；
- `ems_strategy/decision.py`；
- `tests/unit/ems_strategy/test_core_contracts.py`；
- `tasks/TASK-090.md`。

**验证结果：** immutable/slotted、identity、invalid mutation/type/value、public API、forbidden
dependency、focused/full pytest、Ruff、mypy 与 pre-commit。

**关键设计决策：** 不新增 `EMSStrategyBoundary`，不修改 Phase 5～8，不调用 Simulator，
不执行 Constraint/Feasibility，不生成 Actuation、Command 或任何具体 EMS algorithm。

## TASK-091 EMS Strategy Boundary

**背景：** TASK-090 已提供 immutable Context、Strategy descriptor 和 Decision artifacts，
但尚未定义所有具体 EMS strategies 必须遵守的统一调用入口。

**目标：** 新增 abstract、empty-slotted `EMSStrategyBoundary`，冻结
`evaluate(context: EMSContext) -> EMSDecision` contract。

**实现内容：**

- 新增独立 `ems_strategy/boundary.py`；
- 从 `ems_strategy` public API 导出 boundary；
- 文档化 exact `decision.source_context is context` postcondition；
- 使用 test-only `MinimalStrategy` 验证 subclass、返回类型和 identity；
- 验证 boundary 与 test implementation 均无 instance state。

**架构意义：** 未来 Self Consumption、Zero Export、TOU 和 MPC implementation 可以使用
同一调用契约，而 Simulator、Constraint、Runtime 和 Device 继续保持隔离。

**新增文件：**

- `ems_strategy/boundary.py`；
- `tests/unit/ems_strategy/test_strategy_boundary.py`；
- `tasks/TASK-091.md`。

**验证结果：** abstract/signature、statelessness、exact context provenance、public API、
dependency isolation、full pytest、Ruff format/check 与 mypy。

**关键设计决策：** boundary 本身不执行 input normalization、copy、Constraint、Simulator 或
Command；conforming implementation 必须返回引用 exact input context 的 `EMSDecision`。

## TASK-092 EMS Decision Provenance Contract

**背景：** TASK-090 定义 Context、Strategy descriptor 和 Decision，TASK-091 定义统一调用
边界；完成后的 Decision 仍需要一个独立、不可变、只读的 lineage observation artifact。

**目标：** 新增 `DecisionProvenance`，保存 exact Context、Strategy descriptor 和 Decision。

**实现内容：**

- 新增 frozen/slotted `DecisionProvenance`；
- 使用 `is` 验证 Decision 内 source Context 和 source Strategy descriptor；
- 拒绝 value-equal reconstructed source artifacts；
- 从 `ems_strategy` public API 导出 provenance contract；
- 增加 focused identity、immutability、invalid type 和 dependency tests。

**架构意义：** Phase 9 首次能把一次 Strategy Decision 的直接来源作为 immutable evidence
观察，同时不重新执行 Strategy、不重建 Decision，也不把 provenance 变成 history storage。

**新增文件：**

- `ems_strategy/provenance.py`；
- `tests/unit/ems_strategy/test_decision_provenance.py`；
- `tasks/TASK-092.md`。

**验证结果：** exact identity、reconstruction rejection、frozen/slotted、observation-only
dependencies、full pytest、Ruff、mypy 与 `git diff --check`。

**关键设计决策：** 不修改 TASK-090/091 contracts，不保存 Strategy implementation，不调用
Simulator、Constraint、Runtime、Device 或 Command，不引入 serialization 或 mutable state。

## TASK-093 EMS Decision Feasibility Boundary Contract

**背景：** Strategy request 不能直接等同于物理可行结果或 Simulator actuation。TASK-092 已
提供 exact Decision provenance，因此 feasibility 必须显式保留该 evidence，而不是重建。

**目标：** 新增 immutable `FeasibleDecision` 与 abstract `FeasibilityBoundary`，建立请求到可行
结果的架构 seam，不实现约束算法。

**实现内容：**

- FeasibleDecision 保存 exact source Decision 和 exact DecisionProvenance；
- provenance 必须使用 `is` 引用 exact source Decision；
- approved action 独立表达，可保持 source action 或降为 idle，不允许反向生成业务策略；
- approved power 使用 finite non-negative raw kW magnitude；
- boundary 使用 empty slots，无 cache、history 或 instance state；
- provenance 作为显式 keyword-only input，避免 boundary 内部重建 evidence。

**架构意义：** Phase 9 首次明确区分 Strategy request 与 approved feasible result，同时继续保持
`FeasibleDecision != BatterySimulationActuation != Command`。

**新增文件：**

- `ems_strategy/feasibility.py`；
- `tests/unit/ems_strategy/test_feasibility_boundary.py`；
- `tasks/TASK-093.md`。

**验证结果：** abstract/signature、identity/reconstruction、immutability、statelessness、action
contract、dependency isolation、full pytest、Ruff、mypy 与 `git diff --check`。

**关键设计决策：** 不实现 SOC、Battery/Grid constraint、power clipping、Zero Export、TOU、
MPC、Simulator call、Actuation handoff、Runtime、Device 或 Command；不修改既有 contracts。

## 2. 后续追加模板

## TASK-094 EMS Feasible Decision to Simulator Actuation Handoff Contract

**背景：** Phase 9 `FeasibleDecision` 与冻结的 Phase 6
`BatterySimulationActuation` 是独立类型，不能通过修改旧 contract 或伪造类型直接连接。

**目标：** 新增 explicit EMS-to-Simulator adapter boundary，在保持两侧 contract 不变的同时，
建立可审计的 direct identity lineage。

**实现内容：**

- 新增 frozen/slotted `ActuationHandoffResult`；
- 保存 exact Phase 9 `FeasibleDecision` 与 exact existing
  `BatterySimulationActuation`；
- 新增 abstract/stateless `ActuationHandoffBoundary`；
- 使用 identity 验证拒绝 value-equal reconstructed source；
- 冻结 charge 为正、discharge 为负、idle 为零的 Simulator raw kW 映射契约。

**架构意义：** 明确 EMS Layer 到 Simulator Layer 的 adapter seam，同时保持
`FeasibleDecision != BatterySimulationActuation != Command`。

**新增文件：**

- `ems_strategy/handoff.py`；
- `tests/unit/ems_strategy/test_actuation_handoff.py`；
- `tasks/TASK-094.md`。

**验证结果：** abstract/stateless、frozen/slotted、exact source/actuation identities、
reconstruction rejection、signed-power mapping、dependency isolation、full pytest、Ruff、mypy
与 `git diff --check`。

**关键设计决策：** 不修改 Phase 5–8 contracts，不执行 Battery physics、SOC transition、
Constraint、Simulator、Runtime、Device、PCS 或 Command。

## TASK-095 Self Consumption EMS Strategy

**背景：** TASK-090–094 已建立 Strategy request、provenance、feasibility 与 Simulator
handoff contracts，但 Phase 9 尚无具体 Strategy implementation。

**目标：** 实现第一个 concrete `EMSStrategyBoundary`，根据 PV、Load、SOC 与 reserve SOC
facts 产生 self-consumption `EMSDecision` request。

**实现内容：**

- PV surplus 产生 charge request；
- Load deficit 且 SOC 高于 reserve 时产生 discharge request；
- balanced 或不可请求放电时产生 idle request；
- requested power 是未裁剪的 non-negative raw kW magnitude；
- exact `EMSContext` 与 immutable Strategy descriptor identity 得到保留；
- Strategy empty-slotted，不保存 cache、history 或 runtime state。

**架构意义：** Phase 9 首次加入真实业务决策逻辑，同时保持 Strategy 只表达请求，
Feasibility 负责物理可行性，handoff 负责 Simulator sign mapping。

**新增文件：**

- `ems_strategy/self_consumption.py`；
- `tests/unit/ems_strategy/test_ems_self_consumption_strategy.py`；
- `tasks/TASK-095.md`。

**验证结果：** charge/discharge/idle、reserve SOC gate、unclipped request、identity、
statelessness、dependency isolation、full pytest、Ruff、mypy 与 `git diff --check`。

**关键设计决策：** 不执行 SOC limiting、power clipping、Grid/Zero Export constraint、
Simulator、Runtime、Device、PCS、Command、TOU、MPC、Optimization 或 Forecasting；不修改
TASK-090–094 和 Phase 5–8 contracts。

## TASK-096 Zero Export Feasibility Boundary

**背景：** Self Consumption Strategy 已能产生请求，但 Zero Export 属于 feasibility
constraint，不能被塞入 Strategy 或直接变成物理控制。

**目标：** 新增 immutable feasibility evidence 与 abstract/stateless boundary，只表达一个
exact `EMSDecision` 是否满足 Zero Export 可行性。

**实现内容：**

- `ZeroExportFeasibility` 保存 exact Decision、exact DecisionProvenance 与 Boolean status；
- `ZeroExportBoundary` 使用 empty slots，不保存 cache/history/runtime state；
- public evaluation seam 使用 `is` 强制 direct input/output lineage；
- PV-surplus charge request 可保持为 feasible；
- future export risk 只表达为 infeasible，不生成 correction。

**架构意义：** 明确 Zero Export 是 Constraint，不是 Strategy，并保持
Strategy request、feasibility evidence、actuation 与 Command 分离。

**新增文件：**

- `ems_strategy/zero_export.py`；
- `tests/unit/ems_strategy/test_zero_export_feasibility.py`；
- `tasks/TASK-096.md`。

**验证结果：** frozen/slotted、abstract/stateless、Decision/Provenance identities、
reconstruction rejection、feasible/infeasible representation、dependency isolation、full pytest、
Ruff、mypy 与 `git diff --check`。

**关键设计决策：** 不修改 SelfConsumptionStrategy，不执行 clipping、SOC、Grid control、
Simulator、Runtime、Device、Command、TOU、MPC、Optimization 或 Forecasting；不修改既有
contracts。

## TASK-097 Battery Operating Envelope Feasibility Boundary

**背景：** Zero Export feasibility 已建立独立 constraint evidence；Battery 自身的 SOC 与功率
operating envelope 也需要独立表达，不能进入 Strategy 或 Simulator physics。

**目标：** 新增 caller-supplied immutable Battery limits、abstract/stateless evaluation seam 与
identity-preserving feasibility result。

**实现内容：**

- `BatteryOperatingEnvelope` 明确 SOC fraction 与 charge/discharge raw kW limits；
- `BatteryOperatingEnvelopeFeasibility` 保存 exact Decision、Provenance、Envelope 与 Boolean；
- boundary 使用 `is` 强制 direct lineage 并拒绝 reconstructed artifacts；
- tests 演示 charge/discharge、SOC boundary 与 power limit semantics；
- production contract 不包含 clipping 或 correction algorithm。

**架构意义：** Battery physical feasibility 与 Strategy request、Zero Export constraint、
actuation handoff 和 physical execution 保持分离。

**新增文件：**

- `ems_strategy/battery_operating_envelope.py`；
- `tests/unit/ems_strategy/test_battery_operating_envelope.py`；
- `tasks/TASK-097.md`。

**验证结果：** immutable/slotted、exact identity、reconstruction rejection、charge/discharge、
SOC/power boundary、statelessness、dependency isolation、full pytest、Ruff、mypy 与
`git diff --check`。

**关键设计决策：** 不执行 clipping、SOC calculation、Strategy generation、Grid control、
Simulator、Runtime、Device、PCS、Command 或 Optimization；不修改既有 contracts。

## TASK-098 Time Of Use Strategy

**背景：** Phase 9 已有 Self Consumption Strategy；TOU 需要作为独立的业务 Strategy，
不能复用为 Battery/Zero Export constraint 或 Device control。

**目标：** 新增 concrete `TOUStrategy`，通过 immutable caller-supplied tariff configuration
与当前价格事实产生 semantic charge/discharge/idle `EMSDecision` request。

**实现内容：**

- low price request charge，high price request discharge，normal period request idle；
- thresholds 使用 signed finite unscaled CNY/kWh，request powers 使用 positive raw kW；
- exact EMSContext 与 immutable configuration identity 得到保留；
- Strategy frozen/slotted，无 cache、history、runtime state 或 external price lookup。

**架构意义：** 扩展 Phase 9 的可替换 Strategy 集合，同时仍将 SOC、power、Grid 与 execution
职责留在 downstream feasibility/handoff layers。

**新增文件：**

- `ems_strategy/tou.py`；
- `tests/unit/ems_strategy/test_ems_tou_strategy.py`；
- `tasks/TASK-098.md`。

**验证结果：** low/high/normal、threshold inclusion、identity、immutability、invalid config、
dependency isolation、full pytest、Ruff、mypy 与 `git diff --check`。

**关键设计决策：** 不实现 SOC protection、power limit、clipping、Optimization、Forecasting、
MPC、coordinator、Simulator、Runtime、Device、PCS、Command 或 external price service；不修改
existing contracts。

## TASK-100 Strategy Coordinator

**背景：** Phase 9 已有多个独立 Strategy；需要一个明确、可审计的地方协调它们的输出，但不能把协调层扩展为控制器或优化器。

**目标：** 新增 immutable `StrategyCoordinatorConfiguration` 与 `StrategyCoordinator`，让 caller 同时提供 Strategy tuple 和 descriptor identity priority。

**核心契约：** 每个 Strategy 按 caller tuple order 恰好执行一次；priority 只由 caller 提供的 exact `EMSStrategyDescriptor` identity 决定；最终返回原 Strategy 产生的 exact `EMSDecision`。因此 `decision.source_context is context` 和 `decision.source_strategy is selected_strategy.descriptor` 保持成立。reconstructed-but-equal descriptor 会被拒绝。

**架构收益：** Strategy 的业务请求、下游 feasibility 与 physical execution 保持分离。Coordinator 不创建新 Decision，也不创建或重建 `DecisionProvenance`；已有/调用方创建的 provenance evidence 可继续观察同一个 selected decision。

**新增文件：** `ems_strategy/coordinator.py`、`tests/unit/ems_strategy/test_strategy_coordinator.py`、`tasks/TASK-100.md`。

**关键设计决策：** priority 是显式 caller policy，不是隐式 ranking、scoring、weighting 或 optimization；没有 runtime state、cache、history、设备、Command、physical model 或 simulator integration。

## TASK-101 EMS End-to-End Integration Runner

**背景：** TASK-090～100 已建立 Strategy、provenance、feasibility、handoff 与 coordinator；Simulator 1.0 已能确定性执行 24 小时物理模型。需要一个应用层把既有边界组合为完整可审计的流程。

**目标：** 增加 `EMSIntegrationRunner`，以 caller-supplied daily facts、`StrategyCoordinator`、`FeasibilityBoundary` 与 `ActuationHandoffBoundary` 执行 24 个显式步骤，并收集完整 evidence traces。

**核心契约：** 每一步保留 exact `EMSContext → EMSDecision → DecisionProvenance → FeasibleDecision → ActuationHandoffResult → SimulationExecutionTrace` 引用。Strategy、Feasibility 和 Handoff 每步恰好一次；SOC source state 与前一步 battery next state 保持 identity 连续性。

**架构收益：** 应用层只编排 caller-owned 边界；没有新 Strategy、constraint、physical correction、Command、Runtime 或 Device ownership。原有 simulator contracts 与输出保持不变。

**新增文件：** `ems_simulator/ems_integration.py`、`tests/integration/test_ems_integration_runner.py`、`tasks/TASK-101.md`。

**验证结果：** 覆盖 24-step deterministic flow、strategy path/provenance、SOC validity、grid balance、trace identity 与无状态性。

## TASK-102 Forecast Horizon Interface

**背景：** Phase 9 的普通 `EMSContext` 只保存当前 measured facts。未来 TOU/MPC 等策略可能需要 future information，但不能把 prediction、solver state 或 service ownership 塞进 Context。

**目标：** 新增独立 `forecast` package：`ForecastPoint` 表达一个 future timestamp 的 PV、Load 与 optional price prediction；`ForecastHorizon` 表达 caller-supplied ordered points。

**核心契约：** Point frozen/slotted；PV/Load 使用 non-negative finite raw kW，optional price 使用 signed finite raw CNY/kWh。Horizon 只接受 tuple，保留 exact caller tuple 与 point identities，要求 timestamp 严格递增，允许 empty horizon，不排序、去重、补点或创建 prediction。

**架构收益：** 当前 facts 与 future predictions 明确隔离：`EMSContext` 没有 forecast field，Forecast package 也不依赖 EMSContext、Strategy implementation、Simulator 或预测服务。未来 Strategy 只有在独立扩展 API 时才可消费该 artifact。

**新增文件：** `forecast/model.py`、`forecast/__init__.py`、`tests/unit/forecast/test_forecast_contracts.py`、`tasks/TASK-102.md`。

**验证结果：** 覆盖 immutable/slotted、optional price、invalid values、strict order、empty horizon、exact identity、public import 与 EMSContext isolation。
## TASK-099 Peak Shaving Strategy

**背景：** Phase 9 已建立 Self Consumption 与 TOU Strategy。Peak Shaving 作为独立的
business Strategy，只形成负载超过目标时的 discharge request。

**目标：** 新增 immutable `PeakShavingConfiguration` 与 concrete
`PeakShavingStrategy`，根据 exact EMSContext 的 Load 与 caller-supplied demand limit 产生
semantic `EMSDecision`。

**实现内容：**

- Load 超过 demand limit 请求 discharge，requested magnitude 为原始超限差额；
- Load 等于或低于 limit 请求 idle；
- configuration 使用 finite non-negative raw kW，保持 exact identity；
- Strategy frozen/slotted，无 cache、history 或 runtime state。

**架构意义：** Peak Shaving 只表达业务请求，SOC、Battery power、Grid、feasibility 与
execution 保持在下游各自的边界。

**新增文件：**

- `ems_strategy/peak_shaving.py`；
- `tests/unit/ems_strategy/test_ems_peak_shaving_strategy.py`；
- `tasks/TASK-099.md`。

**验证结果：** above-limit discharge、at/below-limit idle、identity、immutability、invalid
configuration、dependency isolation、full pytest、Ruff、mypy 与 `git diff --check`。

**关键设计决策：** 不读取 SOC 或 Battery power limits，不执行 clipping、feasibility、
Simulator、actuation、Optimization、Forecasting、MPC、Runtime、Device、PCS 或 Command；
不修改 existing contracts。

## TASK-103 Forecast-Aware TOU Strategy

**背景：** TASK-102 已将 future predictions 从 current `EMSContext` 分离为 caller-owned `ForecastHorizon`。现有 TOU 只读取 current price，无法以最小方式验证 future tariff 输入。

**目标：** 扩展既有 `TOUStrategy.evaluate` 的 optional keyword-only `forecast_horizon` 输入；不改变 `EMSStrategyBoundary` 或无 forecast 的 TASK-098 行为。

**核心契约：** current low/high threshold 继续优先。仅 current normal price 时，future-only high tariff 请求 charge，future-only low tariff 请求 discharge，mixed/empty/unavailable horizon 请求 idle。Horizon 只在 evaluation 中读取，不被 Strategy 保存、复制或重建。

**架构收益：** `EMSContext` 继续只含 current facts；`EMSDecision` 和 `DecisionProvenance` 保持不变并继续保留 exact Context/descriptor identity。固定 threshold look-ahead 是 concrete Strategy rule，不是 MPC、solver、ranking 或 optimization。

**新增文件：** `tasks/TASK-103.md`；更新 `ems_strategy/tou.py` 与 TOU unit tests。

**验证结果：** 覆盖 legacy no-forecast、future high/low、empty/unavailable/mixed horizon、exact input identity、statelessness 与 dependency isolation。

## TASK-104 Forecast-Aware Peak Shaving Strategy

**Background:** TASK-099 forms a request from current Load, while TASK-102
keeps future predictions in a caller-owned `ForecastHorizon`, outside current
`EMSContext` facts.

**Objective:** Extend `PeakShavingStrategy.evaluate` with an optional
keyword-only `forecast_horizon` input while preserving the no-forecast
TASK-099 behavior.

**Implementation:** A current Load exceeding `demand_limit_kw` remains the
primary discharge request. When current Load is not above the limit, the first
caller-ordered future Load forecast above that limit requests discharge with
its raw-kW excess. Empty and non-exceeding horizons request idle.

**Architecture benefit:** The forecast remains caller-owned and is not stored,
copied, or mutated by the frozen Strategy. The fixed look-ahead rule is not
MPC, optimization, forecast generation, or feasibility evaluation.

**Changed files:** `ems_strategy/peak_shaving.py`,
`tests/unit/ems_strategy/test_ems_peak_shaving_strategy.py`, and
`tasks/TASK-104.md`.

**Key decision:** No SOC, Battery/Grid limit, clipping, `EMSDecision`,
DecisionProvenance, Coordinator, Simulator, or Phase 5–8 contract change.

## TASK-105 MPC Strategy Contract

**Background:** Phase 9 already separates current facts (`EMSContext`), future
facts (`ForecastHorizon`), decision requests (`EMSDecision`), physical
permission (Feasibility), and Simulator handoff (Actuation).

**Objective:** Add immutable `MPCConfiguration` and `MPCStrategyInput`, plus
the abstract empty-slotted `MPCStrategyBoundary`, without introducing an MPC
algorithm or changing the generic Strategy ABI.

**Core contracts:** The input keeps exact identity references to Context,
Horizon, and Configuration. The configuration declares only forecast point
count and explicit control-step duration. An implementation returns the
existing `EMSDecision`, preserving exact Context and strategy descriptor
provenance.

**Architecture benefit:** MPC is frozen as an advanced Strategy seam, not a
bypass around decision provenance, Feasibility, Actuation, or the Simulator.
Forecast stays future information; feasibility remains physical permission;
Actuation remains execution handoff.

**Non-goals:** no solver, LP/QP/MILP, objective weighting, state prediction,
forecast generation, SOC handling, clipping, simulator/runtime/device/command
logic, or Coordinator change.

**Changed files:** `ems_strategy/mpc.py`, `ems_strategy/__init__.py`,
`tests/unit/ems_strategy/test_mpc_strategy_contract.py`,
`tasks/TASK-105.md`, and this record.

## TASK-106 Optimization Core Contracts

**Background:** TASK-105 established MPC as a future Strategy seam using
current `EMSContext` and caller-owned `ForecastHorizon`. An advanced Strategy
needs a solver-independent vocabulary without bypassing existing Decision,
Feasibility, Actuation, or Simulator contracts.

**Objective:** Create an independent `optimization` package with immutable
`OptimizationObjective`, ordered `OptimizationObjectiveCollection`,
identity-preserving `OptimizationProblem`, generic `OptimizationResult`, and
abstract empty-slotted `OptimizationBoundary`.

**Core contracts:** Objectives state only semantic name and minimize/maximize
sense. Problems preserve exact Context, Horizon, and objective collection
references. Results preserve exact source-problem identity and report only a
generic outcome, without producing decisions, physical actions, or commands.

**Architecture benefit:** Optimization answers what plan or result best serves
declared objectives; MPC remains the Strategy that may later translate a
current action into `EMSDecision`; Feasibility and Actuation remain downstream.

**Non-goals:** no solver, LP/QP/MILP, objective weighting algorithm, Battery
prediction, forecast generation, MPC concrete Strategy, Feasibility/Actuation/
Simulator change, Runtime, Device, or Command work.

**Changed files:** `optimization/`, package configuration, focused tests,
`tasks/TASK-106.md`, and this record.

## TASK-107 Optimization Control Plan Contract

**Background:** TASK-106 provides immutable optimization requests and generic
outcomes but deliberately does not represent the future sequence that an
eventual solver could propose.

**Objective:** Add `OptimizationControlStep` and `OptimizationControlPlan` as
solver-independent, immutable contracts for a future semantic control sequence.

**Core contracts:** Each step has caller-supplied timezone-aware time,
existing `DecisionIntent` semantic action, and finite non-negative raw-kW
magnitude. Plans preserve exact source `OptimizationResult`, caller tuple, and
step identities; timestamps must be strictly increasing without automatic
ordering or progression.

**Architecture benefit:** An optimization result describes solving an
optimization request; a control plan describes its proposed future sequence;
a future MPC Strategy alone translates the current plan step to `EMSDecision`.
Feasibility and Actuation remain downstream physical-permission and execution
handoff boundaries.

**Non-goals:** no solver, MPC algorithm, receding-horizon loop, Battery model,
SOC dynamics, feasibility/clipping, Simulator execution, Runtime, Device, or
Command work.

**Changed files:** `optimization/control_plan.py`, its focused tests,
`tasks/TASK-107.md`, package exports, and this record.

## TASK-108 MPC Current Action Extraction Contract

**Background:** TASK-107 expresses a complete proposed future control sequence,
but a plan is not an execution schedule and may not directly trigger future
steps.

**Objective:** Add immutable `MPCCurrentAction` provenance, abstract current
action extraction and decision-translation seams, and one explicit first-step
extractor.

**Core contracts:** A current action preserves exact source plan and selected
step identity. Reconstructed or foreign steps are rejected with identity
membership checks. First-step extraction selects exactly `plan.steps[0]` and
does not mutate or advance the plan. Translation preserves the exact Context
from plan provenance and an exact caller-supplied MPC descriptor in one
existing `EMSDecision`.

**Architecture benefit:** Optimization plans remain future proposals;
`MPCCurrentAction` selects one current interval; only an MPC Strategy request
continues through Feasibility and Actuation. The future sequence is never
executed automatically.

**Non-goals:** no solver, optimizer, repeated receding-horizon loop, clock,
scheduler, automatic progression, SOC/Battery model, feasibility/clipping,
Simulator, Runtime, Device, or Command work.

**Changed files:** `ems_strategy/mpc_current_action.py`, package exports,
focused tests, `tasks/TASK-108.md`, and this record.

## TASK-109 Receding Horizon MPC Cycle Contract

**Background:** TASK-105 through TASK-108 separately establish MPC planning
facts, solver-independent optimization provenance, proposed future plans, and
explicit selection of one current plan step.

**Objective:** Add immutable `MPCCycleInput`, `MPCCycleResult`, and the
abstract empty-slotted `MPCCycleBoundary` to express one complete, traceable
MPC cycle that stops after one current `EMSDecision`.

**Core contracts:** Input preserves exact Context, Horizon, Configuration,
objective collection, and MPC strategy descriptor identities. Result preserves
and validates the exact Input -> Problem -> OptimizationResult ->
OptimizationControlPlan -> MPCCurrentAction -> EMSDecision chain. The decision
must retain the input Context and strategy descriptor, plus the selected
step's exact semantic intent and requested power.

**Architecture benefit:** Receding horizon is made explicit without becoming a
Runtime loop: solve one horizon, select one current action, emit one current
decision, then stop. A later caller may start another independent cycle with
new facts. No future action is scheduled or executed automatically.

**Key decision:** No concrete orchestrator is added because the frozen
`OptimizationBoundary` intentionally yields only `OptimizationResult`; it has
no plan-construction contract. Adding one would be a separate seam, rather
than implicit solver behavior in this task.

**Non-goals:** no solver, plan builder, repeated loop, scheduler, clock,
forecast refresh, state progression, feasibility, Actuation, Simulator,
Runtime, Device, or Command work.

**Changed files:** `ems_strategy/mpc_cycle.py`, package exports, focused tests,
`tasks/TASK-109.md`, and this record.

## TASK-110 Optimization Control Plan Construction Boundary

**Background:** TASK-109 deliberately left the transition from an
`OptimizationResult` to an `OptimizationControlPlan` undefined, because the
frozen solver boundary reports only an outcome and has no plan-construction
contract.

**Objective:** Add immutable `OptimizationControlPlanConstructionInput` and an
abstract empty-slotted `OptimizationControlPlanConstructionBoundary` for that
explicit representation seam.

**Core contracts:** Construction input preserves one exact source result. A
conforming constructor returns an existing EOS control plan that preserves that
exact object as `plan.source_result`; value-equal reconstructed provenance is
not accepted by a conforming construction path.

**Architecture benefit:** Solver outcome, future plan representation, current
action selection, and current decision translation remain independently
replaceable. The new seam ends at the plan and does not execute it.

**Key decision:** No generic production builder is added. Existing result
semantics contain no explicit control-step data, so manufacturing future steps
would invent an optimization outcome rather than represent one.

**Non-goals:** no solver, MPC loop, automatic current-action extraction,
decision translation, feasibility, Actuation, Simulator, Runtime, Device, or
Command work.

**Changed files:** `optimization/control_plan_construction.py`, package
exports, focused tests, `tasks/TASK-110.md`, and this record.

```markdown
## TASK-XXX

**目标：**

**实现内容：**

**架构意义：**

**新增文件：**

**验证结果：**

**关键设计决策：**
```
