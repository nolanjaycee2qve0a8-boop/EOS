# EOS 架构说明

## 1. 文档定位

本文是 EOS Reference Implementation 的软件架构设计说明书。它记录稳定的架构原则、
包职责、依赖方向和演进约束，不替代 TASK 文档或 ADR。

本文描述截至 TASK-059 的架构。TASK-001～037 建立 Decision Kernel，TASK-038～044
建立 Physical Constraint 与 Decision Evaluation Framework，TASK-045～052 建立、
验证并冻结 EMS Capability Layer；TASK-053～055 建立独立 Objective Description、
Activation 与 Objective-Capability Mapping Boundary；TASK-056 建立 descriptor-only
Capability Discovery Boundary；TASK-057 建立 Required-to-Available Capability Matching
Boundary；TASK-058 建立 matched Capability descriptor Activation Boundary；TASK-059
建立 Objective 与完整 Active Capability Collection 的 Composition Boundary。

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

#### Phase 3：TASK-045～TASK-052 — EMS Capability Layer（Completed）

该阶段从 TASK-045 开始，为可独立演进的 EMS 业务能力建立稳定扩展入口。
`EMSCapabilityBoundary` 定义
`evaluate(DecisionContext) -> DecisionIntent`，但不继承或修改
`DecisionContextPolicy`，也不自动接入 Evaluation Integration。Capability 表达业务
目标希望系统做什么；Constraint 继续决定物理上允许什么；Runtime 与 Device 继续负责
后续生命周期和外部执行。TASK-045 建立抽象边界；TASK-046 在该边界上新增第一个
concrete `TOUEnergyCapability`，使用显式 immutable 小时、价格阈值和意图功率 facts
生成 `DecisionIntent`，但不执行 SOC/功率/Grid Constraint，也不接入 Runtime 或
Device。TASK-047 进一步新增 abstract `CapabilityCompositionBoundary`，定义 caller
ordered capability tuple 的 exactly-once evaluation，并返回同序 exact intent tuple；
它不选择、排序、去重、评分或合并 intents。TASK-048 新增 abstract
`IntentResolutionBoundary`，只定义
`tuple[DecisionIntent, ...] -> DecisionIntent` 的未来解析入口；不新增 concrete
resolver，也不定义 priority、weight、score、ranking、selection、optimization 或
arbitration algorithm。TASK-049 新增第二个 concrete Capability：
`SelfConsumptionCapability`，只读取 raw kW 的 PV 与 Load，并按 `PV - Load` 产生
charge、discharge 或 idle candidate intent；它不读取或执行 SOC、Battery/Grid
Constraint、Resolution、Evaluation、Runtime 或 Device 行为。TASK-050 在已接受
`IntentResolutionBoundary` 上新增第一个 concrete
`DeterministicIntentResolutionImplementation`，通过 required immutable
`selected_candidate_index` 返回 caller tuple 中的 exact candidate；不包含 capability
name、hidden priority、weight、score、optimization 或物理约束逻辑。TASK-051 不新增
生产边界或算法，而是通过 end-to-end integration tests 验证现有 Capability、
Composition、Resolution、Constraint Pipeline、Explanation Chain 与 Evaluation Cycle
可以组成完整 Phase 3 决策链，并保持 exactly-once execution 与 exact identity lineage。
TASK-052 对 Phase 3 执行冻结审查：Capability、Composition、Resolution、Constraint、
Evidence、Dependency Direction 与 Legacy Isolation 全部通过。后续修改这些稳定合同
必须通过独立 TASK 和架构审查，不能在新 Capability 中隐式迁移。

#### Phase 4：TASK-053～TASK-059 — Objective & Capability Architecture（Completed）

TASK-053 只建立 EMS Objective 的描述边界。`EMSObjectiveBoundary` 通过
`describe() -> ObjectiveCollection` 返回 immutable objective descriptions；
`ObjectiveDescriptor` 只包含非空的 `name` 与 `description`，
`ObjectiveCollection` 只保存 caller-supplied descriptor tuple。

Objective 回答“EMS 关注什么”，不回答“电池应该做什么”。因此该层没有 concrete
objective、priority、weight、score、optimization、resolver 或 `DecisionIntent`
生成，也不依赖 Kernel、Capability、Constraint、Evaluation、Runtime 或 legacy。
TASK-054 在同一独立 package 中增加 abstract `ObjectiveActivationBoundary` 和 immutable
`ActiveObjectiveCollection`，只表达哪些 exact source descriptors 处于 active 集合。
Activation 保持 source collection、active tuple 与 descriptor identity，不排序、不去重、
不调用 description，也不引入 priority、ranking、conflict resolution、weight、score、
optimization 或 intent generation。
TASK-055 增加 immutable `CapabilityDescriptor` 和 Objective-Capability Mapping contracts，
只表达 exact Objective descriptor 可以由哪些 Capability descriptors 支撑。依赖方向固定为
`objective.mapping -> capability.descriptor`；Capability package 不依赖 Objective。
Mapping 不持有 Capability implementation，不选择、不排序、不评分、不优化、不执行，
也不产生 `DecisionIntent`。
TASK-056 在 Capability package 中增加 abstract `CapabilityDiscoveryBoundary` 与 immutable
`AvailableCapabilityCollection`，只报告 exact `CapabilityDescriptor` references 的可用集合。
Discovery 不连接设备、不读取 CAN/Modbus、不创建 Capability instance，也不执行 matching、
selection、activation、optimization 或 intent generation。
TASK-057 增加 immutable `RequiredCapabilityCollection`、`CapabilityMatch`、
`CapabilityMatchCollection` 与 abstract `CapabilityMatchingBoundary`，只保存 exact
required/available descriptor 关系事实，并通过 immutable `missing_required` tuple 显式记录
未匹配 requirements。每个 required descriptor 必须且只能属于 matched 或 missing 类别，
身份以 `is` 保持。Matching 不定义名称比较规则，也不进行 ranking、scoring、priority、
selection、optimization、fallback、activation 或 intent generation。
TASK-058 增加 immutable `ActiveCapabilityCollection` 与 abstract
`CapabilityActivationBoundary`，以 exact `CapabilityMatchCollection` 为输入，显式保存
matched available descriptors 的 active/inactive 状态。每个 matched descriptor 必须且只能
属于一个状态类别。Activation 不实现 priority、ranking、scoring、selection、optimization、
conflict resolution、fallback、Capability execution 或 `DecisionIntent` generation。
TASK-059 增加 immutable `ObjectiveCapabilityActivationComposition` 与 abstract
`ObjectiveCapabilityActivationCompositionBoundary`，直接保存 exact Objective descriptor 和
exact `ActiveCapabilityCollection`。Composition 不接收第二套 capability subset，因而完整保留
全部 active descriptors；重复 descriptor identity 被拒绝。该边界不进行 selection、ranking、
priority、scoring、optimization、conflict resolution 或 intent generation。

### 2.2 Phase 4 Objective & Capability Architecture

Phase 4 的稳定架构链为：

```text
Objective Layer
        |
        v
Objective-Capability Mapping
        |
        v
Capability Discovery
        |
        v
Capability Matching
        |
        v
Capability Activation
        |
        v
Objective Capability Composition
        |
        v
Future Decision Layer
```

该图描述 dependency 与 evidence progression，不表示一个自动执行的 runtime pipeline。
Phase 4 没有调用 Policy、Constraint、Runtime 或 Device。

每个 boundary 只保证其直接输入与输出之间的 identity preservation。Phase 4 没有建立
Mapping → Required Capability → Discovery → Matching 的自动连接链，也不存在跨这些边界的
自动 identity contract；各阶段所需对象均由 caller 显式提供。

| Boundary | 输入 | 输出 | 职责 | 非职责 |
| --- | --- | --- | --- | --- |
| `EMSObjectiveBoundary` | 无运行时输入 | `ObjectiveCollection` | 描述 EMS 关注事项 | 策略、意图、优化 |
| `ObjectiveActivationBoundary` | `ObjectiveCollection` | `ActiveObjectiveCollection` | 表达 exact objectives 的 active 集合 | priority、conflict resolution |
| `ObjectiveCapabilityMappingBoundary` | Objective collection | `ObjectiveCapabilityMappingCollection` | 表达 Objective 可由哪些 Capability descriptors 支撑 | Capability selection/execution |
| `CapabilityDiscoveryBoundary` | 无调用参数 | `AvailableCapabilityCollection` | 作为 provider contract 报告 available descriptors | 设备扫描、matching、activation |
| `CapabilityMatchingBoundary` | required + available collections | `CapabilityMatchCollection` | 表达 matched relationships 与 explicit missing requirements | ranking、fallback、selection |
| `CapabilityActivationBoundary` | `CapabilityMatchCollection` | `ActiveCapabilityCollection` | 表达 matched descriptors 的 active/inactive 状态 | activation algorithm、execution |
| `ObjectiveCapabilityActivationCompositionBoundary` | Objective + active collection | `ObjectiveCapabilityActivationComposition` | 保存完整 Objective-to-active-Capability 关系 | subset selection、DecisionIntent |

`CapabilityDiscoveryBoundary.discover()` 不接收参数；该 abstract boundary 本身定义 provider
contract，而不是把 provider 作为输入参数。

#### Phase 4 完整性规则

- Objective、Capability 和 relationship artifacts 均为 frozen/slotted immutable contracts；
- 所有 collection 使用 tuple，不接受 list、dict 或 set；
- descriptor 与 source collection 通过 `is` 保持 lineage；
- `CapabilityMatchCollection` 对每个 required descriptor 提供 matched/missing 完整互斥覆盖；
- `ActiveCapabilityCollection` 对每个 matched descriptor 提供 active/inactive 完整互斥覆盖；
- Composition 保存整个 exact active collection，不重建 capability subset；
- Capability package 不反向依赖 Objective package。

#### Phase 4 明确非职责

Phase 4 不包含：

- `DecisionIntent` 或 command generation；
- optimization、ranking、scoring、priority 或 conflict resolution；
- Runtime、scheduler、cache、history 或 persistence；
- Device integration、CAN、Modbus、PCS 或 BMS control。

Future Decision Layer 只是后续演进位置，不属于 Phase 4 已实现能力。任何连接都必须通过新的
独立 TASK 和架构审查，不能修改已冻结的 Objective/Capability contracts。

### 2.3 Phase 5 Decision Formation（TASK-061 started）

TASK-061 建立独立的 `decision_formation.DecisionIntent` immutable artifact，使用显式
`charge`、`discharge`、`idle` action 表达决策语义。该 action 不定义设备功率正负方向、功率
大小、物理可行性、优化结果或执行状态。

```text
Future Decision Formation
        |
        v
decision_formation.DecisionIntent(action)
        |
        v
Future Formation / Resolution / Constraint Boundaries
```

`DecisionIntent` 不等于 `Command`。TASK-061 不形成实际决策、不生成命令、不调用 Capability
implementation，也不依赖 Objective、Constraint、Optimization、Runtime、Execution、Device、
PCS 或 BMS。

现有 `kernel.decision.DecisionIntent(battery_power_intent_kw)` 保持不变。新旧合同位于显式不同
package，没有 inheritance、adapter、alias、automatic conversion 或 migration。Phase 5 后续顺序
规划为 TASK-062 Formation Boundary、TASK-063 Resolution 和 TASK-064 Constraint Evaluation；
这些后续边界尚未实现。

### 2.4 Phase 6 Simulation Core（TASK-065 started）

Phase 6 的依赖方向是：

```text
Future Feasible Decision Artifact
        |
        v
Simulator
        |
        v
Immutable Simulation Observation / Next State
```

Simulation 不调用 Runtime，也不执行 Device。TASK-065 当前只建立：

- explicit zero-based `sequence`；
- explicit positive `duration_seconds`；
- explicit timezone-aware timestamp 或 explicit `None`；
- frozen/slotted `SimulationStepIdentity`。

TASK-065 不定义 PV、Load、Tariff、Battery、Grid、aggregate state、scenario、step result 或 model
composition。Component contracts 必须先在 TASK-066～071 独立完成，TASK-072 才能建立依赖它们的
aggregate contracts。

`SimulationStepIdentity` 不读取 clock、不生成 UUID、不保存 Runtime state。其 duration 单位是 raw
seconds，无隐式缩放；timezone-aware datetime 保持 caller exact identity。

TASK-066 在该 core 之上新增 abstract PV component contract：

```text
SimulationStepIdentity + available_power_kw
        -> PVSimulationInput
        -> PVSimulationModelBoundary
        -> PVSimulationResult(actual_power_kw)
```

该 boundary 不包含 concrete physics、MPPT、inverter、device parameters、Runtime 或 Command。
Result 保持 exact Input identity，actual generation 仅受非负 finite kW 和显式 availability 上界约束。

TASK-067 新增独立 abstract Load component contract：

```text
SimulationStepIdentity + demand_power_kw
        -> LoadSimulationInput
        -> LoadSimulationModelBoundary
        -> LoadSimulationResult(actual_power_kw)
```

Demand 是 caller-supplied exogenous fact。Boundary 不预测负载、不生成 profile、不模拟用户行为，也不
访问 Runtime、Device、Command 或 telemetry。

TASK-068 新增 abstract Tariff component contract：

```text
aware SimulationStepIdentity + explicit import/export CNY/kWh
        -> TariffSimulationInput
        -> TariffSimulationModelBoundary
        -> TariffSimulationResult
```

价格是 signed finite raw facts，允许负值。Boundary 不读取 clock、不选择 TOU window、不预测价格、
不调用 API，也不产生 DecisionIntent。

TASK-069 新增 Battery Simulation Actuation contract：

```text
FeasibleDecisionIntent
        -> BatterySimulationActuation(source_feasible_decision, battery_power_kw)
        -> Future Battery Simulation Model
```

Actuation 保留 exact feasible-decision identity。Battery power 使用 signed finite raw kW：正值充电、
负值放电、零值空闲。它不生成 Command、不执行 Constraint、不推进 Battery state，也不拥有 Runtime、
Device、clock、cache 或 history。Battery model contract 仍保留给 TASK-070。

TASK-070 建立 abstract Battery model contract：

```text
step + immutable source state + exact actuation
        -> BatterySimulationInput
        -> BatterySimulationModelBoundary
        -> BatterySimulationResult(immutable next state, actual power)
```

SOC 是 `[0, 1]` raw fraction；actual power 延续正值充电、负值放电、零值空闲的 signed finite raw kW。
Boundary 不实现 SOC transition、efficiency、degradation、constraint 或 concrete physics。Result 保存 exact
Input 与 next-state references，source state 永不原地修改。

TASK-071 建立 abstract Grid model contract：

```text
step + explicit requested Grid exchange
        -> GridSimulationInput
        -> GridSimulationModelBoundary
        -> GridSimulationResult(actual Grid exchange)
```

Requested 与 actual 都使用 signed finite raw kW：正值 import、负值 export、零值 balanced。Grid boundary
不读取其他 component、不计算系统 balance、不执行 Grid Constraint、Zero Export、Runtime 或 Device。

TASK-072 建立 aggregate simulation contracts：

```text
exact component inputs -> SimulationStepInput
exact component results -> SimulationState
input + state          -> SimulationStepResult
tuple[step inputs, ...] -> SimulationScenario
```

Aggregate 只验证同一 exact step 和 result-to-input identity lineage，不调用 component models、不计算 power
balance、不推进 step。Scenario 保留 caller tuple 与顺序，不排序、不去重、不持有 mutable Runtime state。

TASK-073 通过 integration tests 验证完整 Phase 6 evidence flow。Test-only recording models 各执行一次，
aggregate artifacts 保留 exact component results、Battery feasible-decision provenance 与 caller scenario
order，并且不会触发第二次执行。TASK-073 不修改 production contracts，也不新增 runner、Runtime、
Scheduler、Device、Command 或 power-balance calculation。

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
- `IntentResolutionBoundary`：多个 capability candidates 如何进入未来单一意图解析入口？
- `EMSObjectiveBoundary`：EMS 关注事项如何以不可变描述表达，而不产生决策意图？
- `ObjectiveActivationBoundary`：哪些已描述 objective 处于 active 集合，如何保持其身份？
- `ObjectiveCapabilityMappingBoundary`：Objective 与 Capability descriptors 如何表达关系？
- `CapabilityDiscoveryBoundary`：哪些 Capability descriptors 被报告为 available？
- `CapabilityMatchingBoundary`：Required 与 Available descriptors 的关系事实如何表达？
- `CapabilityActivationBoundary`：已匹配 Capability descriptors 的 active/inactive 状态如何表达？
- `ObjectiveCapabilityActivationCompositionBoundary`：Objective 与完整 active Capability 集合的关系如何表达？

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
- 为多个独立 candidate intents 定义未来单一 intent resolution seam；
- 允许未来业务能力独立演进。

**主要对象**

- `EMSCapabilityBoundary`
- `CapabilityCompositionBoundary`
- `DeterministicIntentResolutionImplementation`
- `DeterministicIntentResolutionParameters`
- `IntentResolutionBoundary`
- `SelfConsumptionCapability`
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

TASK-047 的 `CapabilityCompositionBoundary` 定义
`evaluate(context, capabilities) -> tuple[DecisionIntent, ...]`。Caller tuple 位置是
权威顺序；每个位置 exactly once，重复位置不去重，返回 exact intent references。
Boundary 不把多个 intent 解析为单个结果，不提供 selection、priority、score、
arbitration 或 conflict resolution。生产 package 中没有 concrete composition
implementation。

TASK-048 的 `IntentResolutionBoundary` 定义
`resolve(candidates: tuple[DecisionIntent, ...]) -> DecisionIntent`。该抽象边界位于
composition candidates 与 Constraint source intent 之间，只固定 immutable tuple
输入和单一 intent 输出类型。它不规定 empty/single/conflicting candidates 的行为，
不规定输出 identity，也不实现 priority、weight、score、ranking、selection、merge、
optimization 或 arbitration。生产 package 中没有 concrete resolver。

TASK-049 的 `SelfConsumptionCapability` 继承 `EMSCapabilityBoundary`，使用
`battery_power_intent_kw = pv_power_kw - load_power_kw` 生成 raw kW candidate：
正值充电、负值放电、零值空闲。它只读取 PV 与 Load，不检查 SOC、reserve SOC、
battery limit、Grid/export limit、price 或 time。TASK-037 的
`SelfConsumptionPolicy` 保持独立，TASK-049 不对 Policy contract 进行迁移、适配或
替换。

TASK-050 的 `DeterministicIntentResolutionParameters` 是 frozen/slotted 配置，只
保存 required、unitless、zero-based `selected_candidate_index`。
`DeterministicIntentResolutionImplementation` 继承并保持
`IntentResolutionBoundary.resolve(candidates)` 契约，返回
`candidates[selected_candidate_index]` 的 exact identity。它不检查 capability name
或 type，不包含 TOU/Self Consumption special case，不比较 intent value，也不执行
Constraint、Evaluation、Runtime 或 Device。

### 5.5 `decision_formation`

Phase 5 决策形成语义合同包。TASK-061 当前只包含：

- frozen/slotted `DecisionIntent`；
- exact `charge`、`discharge`、`idle` action validation；
- 与 Command、设备方向和既有 numeric Intent 的显式分离。

该 package 只依赖 Python standard library，不依赖 Kernel、Objective、Capability、Constraint、
Optimization、Runtime、Execution 或 Device。

### 5.6 `simulator`

Phase 6 deterministic simulation package。TASK-065 当前只公开 frozen/slotted
`SimulationStepIdentity`，提供显式 sequence、seconds duration 和 optional aware timestamp contracts。

**依赖方向**

```text
simulator.core -> simulator.validation -> Python standard library
```

**当前不负责**

- PV、Load、Tariff、Battery 或 Grid modeling；
- aggregate Simulation State、Scenario、Step Input 或 Result；
- Runtime、scheduler、thread 或自动 step progression；
- Device、Command、Dispatch、PCS/BMS 或协议；
- Optimization、forecast、persistence、cache 或 history。

TASK-066 进一步提供 `PVSimulationInput`、`PVSimulationResult` 与 abstract
`PVSimulationModelBoundary`。PV package 只依赖 simulation core/local validation，不访问 Runtime、
Device、Command、weather、MPPT 或 inverter，也不提供 concrete model。

TASK-067 提供 `LoadSimulationInput`、`LoadSimulationResult` 与 abstract
`LoadSimulationModelBoundary`。Load package 同样只依赖 core/local validation，不包含 forecast、user
behavior、Demand Response、Runtime、Device 或 concrete model。

TASK-068 提供 `TariffSimulationInput`、`TariffSimulationResult` 与 abstract
`TariffSimulationModelBoundary`。Tariff package 只依赖 core/local validation，不依赖 Capability、
Policy、Runtime、Device、external API、forecast 或 concrete model。

TASK-069 提供 frozen/slotted `BatterySimulationActuation`。它依赖现有 immutable
`FeasibleDecisionIntent` contract，保存 exact source identity，并公开 signed finite raw kW 的
充电（正）、放电（负）、空闲（零）语义。它不包含 Battery physics、state transition、Runtime、
Device、Command 或 concrete model。

TASK-070 进一步提供 `BatterySimulationState`、`BatterySimulationInput`、
`BatterySimulationResult` 与 abstract `BatterySimulationModelBoundary`。Battery state/Input/Result 均为
frozen/slotted artifacts；Boundary 只定义 replaceable transition seam，不包含 concrete Battery physics、
Runtime、Device、Command、Constraint、cache 或 history。

TASK-071 提供 `GridSimulationInput`、`GridSimulationResult` 与 abstract
`GridSimulationModelBoundary`。Grid package 只依赖 simulation core/local validation，不依赖其他 component、
Constraint、Runtime、Device 或 Command。系统 power balance 与 aggregate composition 保留给 TASK-072。

TASK-072 提供 `SimulationStepInput`、`SimulationState`、`SimulationStepResult` 与
`SimulationScenario`。这些 frozen/slotted artifacts 只依赖已审核 component contracts，并以 identity
验证跨组件 step 与 result/input provenance。它们不构成 simulation runner、Runtime、Scheduler 或
model orchestration。

TASK-073 仅增加 integration validation。所有 concrete recording models 都位于 tests，生产
`simulator` package 与公开 API 保持不变。

### 5.7 `kernel/runtime`

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

### 5.8 `kernel/execution`

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
