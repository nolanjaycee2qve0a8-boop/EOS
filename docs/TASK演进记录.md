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

## 2. 后续追加模板

```markdown
## TASK-XXX

**目标：**

**实现内容：**

**架构意义：**

**新增文件：**

**验证结果：**

**关键设计决策：**
```
