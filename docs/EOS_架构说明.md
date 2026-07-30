# EOS 架构说明

## 1. 文档定位

本文是 EOS Reference Implementation 的软件架构设计说明书。它记录稳定的架构原则、
包职责、依赖方向和演进约束，不替代 TASK 文档或 ADR。

本文描述截至 TASK-037 的架构。TASK-001～036 建立了 EMS 算法运行所需的输入、
输出、策略、约束、生命周期和编排边界；TASK-037 在这些边界之上首次加入具体但
严格限域的自发自用策略。

## 2. 架构目标

EOS 的目标不是提供一个不可拆分的“万能 EMS 类”，而是提供一个可解释、可重放、
可替换并能长期演进的 Energy Decision Kernel。

核心约束是：

- Architecture drives implementation；
- Kernel is stable；
- Capability evolves；
- Replay is a first-class feature；
- Domain objects are immutable；
- Runtime owns state transitions；
- Capability must not modify Kernel architecture。

### 2.1 当前演进阶段

#### Phase 1：TASK-001～TASK-037 — Decision Kernel

该阶段建立不可变领域对象、状态、决策上下文、策略合同、意图、约束、生命周期、
编排、journal、replay、audit 和 legacy isolation。目标是完成 EMS 算法可以稳定运行
的决策基础设施。TASK-037 的 `SelfConsumptionPolicy` 在这些边界上首次产生真实
能源管理意图，但仍然只负责表达策略意图。

#### Phase 2：TASK-038～TASK-044 — Physical Constraint + Decision Evaluation Framework

该阶段从 TASK-038 开始，将策略意图限制到物理可行范围。
`BatteryConstraintImplementation` 是第一个具体物理约束实现：它根据 SOC、
reserve SOC 和最大充放电功率生成 `FeasibleDecisionIntent`，同时保持 Policy、
Runtime、Execution 和 Device 边界不变。TASK-040 进一步建立
`GridConstraintBoundary`，为未来并网侧物理约束提供抽象入口，但尚未实现进口限制、
出口限制或 zero-export 算法。TASK-041 在该入口上实现第一个具体
`GridPowerLimitConstraintImplementation`，通过显式 immutable baseline、进口上限和
出口上限限制 projected grid exchange。TASK-042 新增无状态
`ConstraintEvaluationPipeline`，由调用者通过 tuple 显式提供多个 constraint 的确定
顺序，Policy 和 Runtime 均不感知该顺序。TASK-043 新增 immutable
`ConstraintExplanationChain`，按完成顺序保存每个 constraint stage 的 exact
source/feasible identity、adjusted 状态和 caller-supplied reason，但不重新执行或
解释 constraint。TASK-044 新增独立 `DecisionEvaluationIntegration`，将 Assembler、
Policy、单次 Constraint Pipeline、Explanation Chain 与 Cycle 组合为一次完整评估，
并通过 immutable result 同时保存 exact cycle 和 exact chain。

#### Phase 3：TASK-045+ — EMS Capability Layer

该阶段从 TASK-045 开始，为可独立演进的 EMS 业务能力建立稳定扩展入口。
`EMSCapabilityBoundary` 定义
`evaluate(DecisionContext) -> DecisionIntent`，但不继承或修改
`DecisionContextPolicy`，也不自动接入 Evaluation Integration。Capability 表达业务
目标希望系统做什么；Constraint 继续决定物理上允许什么；Runtime 与 Device 继续负责
后续生命周期和外部执行。TASK-045 建立抽象边界；TASK-046 在该边界上新增第一个
concrete `TOUEnergyCapability`，使用显式 immutable 小时、价格阈值和意图功率 facts
生成 `DecisionIntent`，但不执行 SOC/功率/Grid Constraint，也不接入 Runtime 或
Device。

## 3. 核心架构原则

### 3.1 Boundary First Design

先定义边界，再实现能力。每个边界回答一个明确问题：

- `EnergySystemState`：物理系统当前是什么状态？
- `DecisionContext`：本次决策能看到什么？
- `DecisionContextPolicy`：策略如何被调用？
- `DecisionIntent`：策略希望系统做什么？
- `DecisionConstraintBoundary`：意图如何进入可行性判断？
- `ConstraintExplanationChain`：多个已完成约束阶段如何形成有序解释证据？
- `DecisionEvaluationCycle`：一次完成的评估包含哪些证据？
- `DecisionEvaluationOrchestrator`：这些边界以什么顺序协作？
- `DecisionEvaluationIntegration`：完整新决策路径如何只执行一次并保存全部证据？
- `EMSCapabilityBoundary`：业务能力如何在不修改 Kernel 的情况下表达决策意图？

边界稳定以后，具体策略、约束和设备适配器可以独立演进。

### 3.2 Immutable Data Contract

领域数据优先使用：

```python
@dataclass(frozen=True, slots=True)
```

不可变不是只为了防止误赋值，还用于：

- 保证一次决策输入在整个生命周期内不变；
- 让 replay 和 audit 观察同一证据；
- 避免 policy、constraint 或 runtime 暗中修改上游对象；
- 让并发、测试和错误定位更可控。

可变集合不能隐藏在 frozen dataclass 中。公共集合使用 tuple，领域引用本身也应指向
已经通过不可变契约验证的对象。

### 3.3 Dependency Direction

依赖应从协调层指向稳定合同，而不是从领域对象反向指向执行系统：

```text
physical observations
        |
        v
system_state
        |
        v
decision contracts
        |
        v
policy / constraint implementations
        |
        v
orchestration
        |
        v
future execution adapters
```

禁止的反向依赖示例：

```text
DecisionIntent -> dispatcher
DecisionContext -> runtime
EnergySystemState -> policy
ConstraintExplanation -> persistence
```

### 3.4 Legacy Isolation

已有运行路径不能因为新架构边界出现而被隐式迁移。EOS 当前保留：

- legacy `EMSPolicy`：`EnergySystemContext -> DecisionResult`；
- new `DecisionContextPolicy`：`DecisionContext -> DecisionContextResult`。

两条路径使用不同输入和输出合同。新代码不能通过继承、adapter、alias 或 overload
悄悄改变 legacy 行为。

### 3.5 Identity Preservation

EOS 不只关心值相等，还关心生命周期证据是否来自同一个对象。关键关系使用 `is`
验证，例如：

```python
cycle.source_intent is cycle.result.intent
cycle.explanation.feasible_intent is cycle.feasible_intent
cycle.explanation.source_intent is cycle.source_intent
```

未发生约束调整时，`cycle.feasible_intent.intent is cycle.source_intent`。发生阻止或
裁剪时，feasible inner intent 是新的 immutable 对象；Cycle 同时保留 source 与
feasible 两条 exact identity。

因此在生命周期边界中禁止：

- `copy()`；
- `deepcopy()`；
- 序列化后重建；
- 为“规范化”而创建值相等的新对象。

身份保持使 audit、explanation 和 replay 能说明“观察到的是同一次执行证据”。

## 4. 为什么不是一个 EMS 大类

一种常见设计是：

```python
class EMS:
    def decide(self): ...

    def control(self): ...
```

这种设计短期简单，但会逐渐把以下职责混在一个对象中：

- 状态采集；
- 时间和电价输入；
- 策略计算；
- SOC 与功率限制；
- 命令生成；
- 协议转换；
- 设备控制；
- 重试、日志和持久化。

结果通常是：

- 算法无法脱离设备做确定性测试；
- 输入在决策过程中被修改；
- 控制失败与策略失败难以区分；
- 替换算法会影响 runtime；
- replay 实际上变成重新执行；
- 很难证明一次解释对应哪次真实决策。

EOS 采用多个边界对象，是为了让每个层次只有一个变化原因：

```text
事实 -> 上下文 -> 策略意图 -> 可行性 -> 生命周期证据 -> 执行
```

多一个明确边界，通常比少一个隐式责任更便宜。

## 5. Kernel 与 Capability 包职责

### 5.1 `kernel/system_state`

**职责**

- 表达电池、PCS、PV 和电网的物理观测；
- 维护单位、范围和功率符号；
- 聚合为 `EnergySystemState`；
- 保持组件对象身份。

**不负责**

- 电价、负荷等外部决策事实；
- 策略、预测或优化；
- 命令与设备通信；
- runtime 状态推进。

**主要对象**

- `BatteryState`
- `PCSState`
- `PVState`
- `GridState`
- `EnergySystemState`

### 5.2 `kernel/decision`

**职责**

- 定义不可变决策输入和输出；
- 定义语义意图及约束结果；
- 装配 `DecisionContext`；
- 验证一次评估生命周期的身份关系；
- 保留 legacy decision contracts。

**主要对象**

- `DecisionContextAssembler`
- `DecisionContext`
- `DecisionContextResult`
- `DecisionIntent`
- `DecisionConstraintBoundary`
- `BatteryConstraintImplementation`
- `GridConstraintBoundary`
- `GridPowerLimitConstraintImplementation`
- `ConstraintEvaluationPipeline`
- `FeasibleDecisionIntent`
- `ConstraintExplanation`
- `ConstraintExplanationEntry`
- `ConstraintExplanationChain`
- `DecisionEvaluationCycle`
- legacy `DecisionResult`、`DecisionPipeline`、`DecisionPolicy`

**不负责**

- 设备协议；
- runtime 循环；
- 命令执行；
- EMS 策略优化、runtime 执行或设备控制。

`BatteryConstraintImplementation` 是 Phase 2 的第一个 concrete constraint。它通过
构造阶段持有一次评估所需的 immutable SOC、reserve SOC 和功率限制 facts，保持
`DecisionConstraintBoundary.evaluate(intent)` 契约不变。它不拥有 history、cache
或 runtime state。

TASK-039 将 `DecisionEvaluationCycle.intent` 明确升级为 `source_intent`。Policy
原始意图始终来自 `DecisionContextResult.intent`；constraint 输出通过
`FeasibleDecisionIntent.intent` 保存。两者在未调整时可以是同一对象，在约束调整后
可以是两个不同的 immutable 对象。

TASK-040 新增 `GridConstraintBoundary`，它继承并保持
`DecisionConstraintBoundary.evaluate(intent)` 的通用签名。Boundary 使用空 slots，
不保存 grid facts，也不实现 import limit、export limit 或 zero-export 行为。未来具体
实现可通过构造注入明确定义的 immutable grid facts，而不会污染 Policy、Orchestrator
或通用 constraint contract。

TASK-041 的 `GridPowerLimitConstraintImplementation` 通过构造接收
`grid_power_baseline_kw`、`max_import_power_kw` 和 `max_export_power_kw`。所有字段
都是 literal kW；baseline 正值表示进口、负值表示出口。它使用
`projected_grid_power_kw = baseline + battery intent`，限制 projected grid power
后反推出 feasible battery intent。实现不修改 `DecisionIntent`、Policy、两个抽象
constraint contracts 或 source/feasible lineage。

TASK-042 的 `ConstraintEvaluationPipeline` 接收 source intent 和 caller-supplied
constraint tuple。Tuple 位置是权威顺序；Pipeline 不排序、不去重、不保存 constraint
实例。每一阶段接收上一阶段的 exact inner intent，最终返回最后一阶段的 exact
`FeasibleDecisionIntent`。空 tuple 返回引用 exact source intent 的 wrapper。该边界
不实现 optimization、priority、conflict resolution、runtime 或 device behavior。

TASK-043 的 `ConstraintExplanationEntry` 保存一个 completed constraint stage 的
exact source、exact feasible、identity-based adjusted flag 与 caller-supplied
reason。`ConstraintExplanationChain` 使用 tuple 保存多个 Entry，验证首阶段 source、
逐阶段 feasible-to-source continuity 和 exact final wrapper。Reason 是 opaque
evidence，不从 SOC、power、grid、price 或 device facts 推理。既有
`ConstraintExplanation`、`DecisionEvaluationCycle`、Policy 和 Constraint contracts
均保持不变。

### 5.3 `kernel/policy`

**职责**

- 定义 legacy 与 new policy 扩展合同；
- 提供新 policy 的实现扩展点；
- 协调一次新决策评估。

**主要对象**

- legacy `EMSPolicy`
- `DecisionContextPolicy`
- `DecisionContextPolicyImplementation`
- `DecisionEvaluationOrchestrator`
- `DecisionEvaluationIntegration`
- `DecisionEvaluationIntegrationResult`
- `SelfConsumptionPolicy`

**不负责**

- 保存 policy 或 constraint 实例；
- 拥有 runtime、clock、dispatcher 或 device；
- 自动迁移 legacy 路径；
- 让具体策略承担 constraint、runtime、dispatch 或 device 职责。

`SelfConsumptionPolicy` 是第一个 concrete implementation。它只输出
`DecisionContextResult(DecisionIntent)`，不执行 SOC/功率约束，也不生成命令。

TASK-044 的 `DecisionEvaluationIntegration` 接收 caller-supplied Policy、constraint
tuple、对应 reason tuple 和全部显式 context facts。它调用 Assembler 与 Policy，
再调用 `ConstraintEvaluationPipeline` 一次；每个底层 Constraint exactly once。
Immutable observing decorator 在同一次调用中保存 exact stage input/output，不重跑
constraint。随后创建 exact Explanation Chain、旧 `ConstraintExplanation` 和 Cycle。
`DecisionEvaluationIntegrationResult` 保存 exact cycle 与 exact chain。既有
`DecisionEvaluationOrchestrator` 保持不变并继续服务早期单 Constraint 路径。

Policy package 的责任是产生和协调决策意图，不负责执行控制。

### 5.4 `capability`

**职责**

- 定义 EMS 业务能力的稳定扩展入口；
- 接收 immutable `DecisionContext`；
- 返回 semantic `DecisionIntent`；
- 允许未来业务能力独立演进。

**主要对象**

- `EMSCapabilityBoundary`
- `TOUCapabilityParameters`
- `TOUEnergyCapability`

**不负责**

- 修改或继承 `DecisionContextPolicy`；
- 执行 Battery/Grid/SOC/功率约束；
- 拥有 runtime、dispatcher、device、cache 或 history；
- 生成 command 或控制 PCS/BMS；
- 执行 optimization、forecast、tariff lookup 或设备控制。

TASK-045 只建立 abstract、empty-slotted contract。依赖方向是
`capability -> kernel.decision`；Kernel 不反向导入 Capability。现有 Policy 与
Evaluation Integration 均保持不变，未来组合必须由单独 TASK 和 ADR 批准。

TASK-046 的 `TOUEnergyCapability` 继承该边界，并通过 frozen/slotted
`TOUCapabilityParameters` 接收 caller-supplied 本地小时 tuple、CNY/kWh 价格阈值和
raw kW 意图幅值。它只读取 `DecisionContext.timestamp.hour` 与
`electricity_price_cny_per_kwh`，返回 charge、discharge 或 idle
`DecisionIntent`。它不持有系统 clock，不查询 tariff，不预测或优化，也不执行任何
Constraint、Integration、Runtime、Dispatch 或 Device 行为。

### 5.5 `kernel/runtime`

**当前职责**

legacy 路径已经提供不可变 tick、journaled tick、dispatch progression、trace、replay、
audit 和 explanation 等生命周期边界。

**未来职责**

- 只有经过明确 TASK 和 ADR 批准后，才可接入新的 DecisionContext 路径；
- 负责确定性生命周期推进，而不是策略算法；
- 负责失败边界和阶段顺序，而不是设备协议；
- 保持 replay 为观察，不把 replay 变成重新执行。

**不负责**

- EMS 策略计算；
- 设备控制细节；
- 隐式缓存或全局运行状态；
- 在观察对象构造时推进系统。

### 5.6 `kernel/execution`

**当前职责**

legacy 路径提供 `PolicyExecutor` 和 journaled execution service，用于把已有 policy
合同接入确定性生命周期。

**未来职责**

- 接收已经完成决策与约束的产物；
- 通过明确 adapter 协调命令生成或外部执行；
- 保证异常传播、对象身份和调用次数可测试；
- 与协议适配器保持分离。

**不负责**

- 重算 policy；
- 修改 context、intent 或 result；
- 在执行阶段补做策略约束；
- 直接内置 CAN、Modbus、MQTT 或 PCS/BMS 细节。

## 6. 其他关键包

| Package | 责任 |
| --- | --- |
| `kernel/domain` | legacy immutable Snapshot、Mission、Command、Event |
| `kernel/asset` | 能源资产定义，不含运行状态或控制行为 |
| `kernel/state` | 第一代资产状态与 EnergySnapshot |
| `kernel/context` | legacy `EnergySystemContext` |
| `kernel/power` | 不可变功率流及符号、平衡验证 |
| `kernel/event` | EventRecord、EventJournal 与 replay |
| `kernel/cycle` | legacy EMSCycle 和 journaled cycle |
| `kernel/dispatch` | CommandDispatcher 与 CommandExecutor 边界 |

## 7. Legacy EMSPolicy 与 DecisionContextPolicy

### 7.1 Legacy 路径

```text
EnergySystemContext
        |
        v
EMSPolicy
        |
        v
DecisionResult(commands, events)
        |
        v
legacy runtime / execution
```

该路径已经被多个 runtime、cycle、journal 和 dispatch 合同使用。直接修改会破坏大量
经过 review 的行为和 replay 证据。

### 7.2 New 路径

```text
EnergySystemState
        |
        v
DecisionContextAssembler
        |
        v
DecisionContext
        |
        v
DecisionContextPolicy
        |
        v
DecisionContextResult(DecisionIntent)
        |
        v
constraint / evaluation cycle
```

新路径刻意不让 policy 输出 commands 或 events，从而把策略语义与设备执行分离。

### 7.3 为什么并存

- 输入模型不同；
- 输出模型不同；
- 生命周期消费者不同；
- legacy 已稳定且具备完整回归测试；
- 新路径仍在逐步建立约束、命令生成和执行边界。

并存不是重复设计，而是受控迁移所需的隔离期。

## 8. 未来迁移策略

迁移必须通过独立 TASK 和 ADR，不能在具体策略中顺便完成。建议顺序：

1. 完成具体 `DecisionContextPolicyImplementation`；
2. 完成真实 constraint implementations；
3. 定义 feasible intent 到 command generation 的独立边界；
4. 定义新路径的 execution result、journal 和 replay 证据；
5. 用并行测试验证新旧路径语义；
6. 明确外部调用者迁移计划；
7. 只有在 legacy consumers 全部迁移后，才能讨论弃用；
8. 删除 legacy 合同必须是单独、可审查的架构决策。

迁移期间禁止：

- 让 `DecisionContextPolicy` 继承 `EMSPolicy`；
- 用 adapter 假装两种 result 等价；
- 把 `DecisionIntent` 自动转换为 legacy commands；
- 修改 runtime 以同时猜测两种输入类型；
- 添加兼容 alias 掩盖合同差异。

## 9. 架构审查清单

每个新 TASK 至少检查：

- 是否改变了已通过 review 的公开合同？
- 新对象是否 immutable、slotted，并且没有深层可变容器？
- 是否保持 exact object identity？
- 是否引入反向依赖？
- policy 是否承担 constraint 或 execution？
- runtime 是否承担算法或设备协议？
- observation 是否触发执行？
- 是否新增 cache、history、timestamp、UUID 或 persistence？
- legacy 路径是否保持不变？
- 文档与 TASK 演进记录是否同步？

## 10. 文档维护

以后每个 TASK 必须同步检查：

- `docs/EOS_学习手册.md`
- `docs/EOS_架构说明.md`
- `docs/TASK演进记录.md`

文档变更应与代码事实一致。未来设计可以记录为“规划”或“非目标”，不能写成已经具备
的能力。
