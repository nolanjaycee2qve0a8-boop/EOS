# EOS 架构说明

## P0.4 Transport-Neutral Device Adapter Boundary

P0.4 在 P0.3 语义与未来 PCS/BMS I/O 之间增加事实边界，不是 controller 或真实设备接线。它保留 P0.1 observation/capability/health 类型，P0.1 仍拥有 freshness 和 safety，P0.3 仍拥有 command authority、reconciliation 与 lifecycle。adapter 只接受从当前 caller/admitted identity 和 safety-final request 产生的一次性 transmission request；zero 是明确消息，ACK 和 actual telemetry 独立到达。无协议、网络、线程、HIL、持久化、硬件控制或自动重试。

## P0.3 Controlled Edge Runtime

P0.3 是 transport-neutral、caller-driven 的 runtime composition，不是 production Runtime。每个明确 tick 复用 P0.2 起点 fault snapshot，并保留 P0.1 safety、ACK、actual telemetry、SOC 与 lifecycle reconciliation。软件 SAFE_IDLE 不能证明硬件已经归零。

> **P0.3 Stage 2B 边界补充：** 每 tick 的 serializable audit evidence 明确分开 caller
> request、safety-final request、ACK accepted power、expected actual 和 Simulator actual
> telemetry；actual telemetry 是执行事实权威，ACK 不是完成。对账用单一稳定风险顺序保留
> primary 与全部 secondary reasons。trace 的严格 schema、UTC/finite-number 与
> tick/time/state/SOC linkage 只用于审计；它不能恢复 Runtime、Simulator、lifecycle book
> 或 P0.2 authority，也没有数据库、重启恢复、协议、线程、HIL 或硬件控制能力。

P0.3 stage 2A 的 runtime state 是 admission evidence，不是 PCS/BMS hardware state。统一 guard
记录每个 tick 的 state-before、state-after 与 reason：陈旧/未知事实等待；链路、可用性或未结
lifecycle 退化；软件安全空闲保持零请求；critical/E-stop/意外非零 actual 故障；显式 shutdown
终结。只有 READY-start 与完整 P0.1 readiness 才会交付一个新非零 command。validation
orchestration 不反向改变控制，也不属于 production Runtime。

P0.3 command-origin guard 只允许当前 caller 的原始 command 被 admission；`tick(None)`
产生 `none` origin，不能从 trace、lifecycle、ACK、actual、safety-final request 或恢复状态制造
替代 command。每个 audit step 保留 caller/admitted command、封闭 origin 和自动生成=false，
但这些序列化事实不构成 retry、resume、persistent recovery 或 command authority。

> **P0.2 边界补充：** `edge_runtime.device_simulator` 位于 P0.1 合同之上的确定性虚拟
> PCS/BMS 与故障注入层。它显式推进虚拟时间，输出 P0.1 safety request、ACK 和 later actual
> telemetry 的独立证据，不反向修改冻结控制链。它不是 P0.3 Runtime loop，也不包含协议、
> HIL、硬件或现场能力。
> P0.2 仅把“即时 accepted、未过期 ACK”应用为当前 step 的 virtual actual response；其余
> ACK 情况均 fail-closed 为零功率。fault target/parameter 由白名单约束，warning retained
> 而 critical fail-closed；step 仅在起点采样 `[activation_at, clear_at)`。
> 这是 simulator policy，不能推断真实 PCS 无 ACK 时必然未执行：未来 Runtime 必须仍以 actual
> telemetry 为执行事实并处理 ACK 丢失/迟到的不确定性；P0.2 不实现该 production reconciliation。

> **P0.1 边界补充：** Residential EMS 1.0 的 A-F 控制与仿真验证已冻结。后续
> `edge_runtime` 是独立、transport-neutral 的设备边界合同层：它不属于现有生产
> Runtime，不反向改变策略或 Simulator。PCS/BMS actual telemetry 才是执行事实；
> 命令与 ACK 仅是请求/回执证据。P0.1 的 publication gate 管理证据发布，不控制设备。
> 详见 `architecture/specification/RESIDENTIAL_EDGE_RUNTIME_BOUNDARY.md` 与 ADR-088。
> P0.1 的 Effective capability 只能从 BMS/PCS facts 在安全层内派生；只有 `READY`
> health、完整 recovery checks 与无 P0.1-blocking `CRITICAL` fault 才可接受新主动功率。
> lifecycle 的 completed 需要在 `execution_started_at` 后、命令 expiry 前的实际遥测证明，
> 绝非 ACK 或软件 SAFE_IDLE 的替代。反序列化 record 仅为审计 evidence，不能恢复权威 book；
> supersede 必须原子登记完整、且高于 book 全局最高 sequence 的 successor；失败不能留下
> predecessor 或索引的部分写入。P0.1 只保留有真实 producer 的 lifecycle 状态，并由专用
> 方法实际调用内部 transition guard；没有公共通用状态跳转入口。

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

## 11. Phase 6 Architecture Freeze（TASK-074）

TASK-074 正式冻结 TASK-065～073 的 Simulation contracts。当前稳定依赖方向为：

```text
completed feasible decision evidence
        |
        v
immutable simulator component contracts
        |
        v
immutable aggregate simulation evidence
```

冻结规则：

- component input 保存 exact step identity；
- component result 保存 exact component input；
- aggregate state/result 保存 exact inputs/results；
- Battery actuation 保存 exact feasible decision；
- scenario 保存 caller tuple identity、element identity 与顺序；
- abstract model boundaries 无实例状态，production simulator 不提供 concrete model；
- aggregate artifacts 不执行 model，不推进 step，不拥有 Runtime state。

Phase 6 package 允许依赖既有 feasible-decision contract 作为 Battery provenance；Kernel、Runtime、
Execution、Dispatch 与 Device 不反向依赖 simulator。Simulation actuation 不得被解释为 Device Command。

Phase 6 当前明确不具备 production physics、power balance、SOC transition、runner、scheduler、automatic
progression、Device integration 或 persistence。完整冻结报告见
`docs/phase-summary/EOS_Phase6_Simulation_Architecture_v1.0.md`。

## 12. Phase 7 Simulation Model Binding（TASK-075）

Phase 7 从 caller-supplied model ownership contract 开始，但尚未引入 executor：

```text
existing component boundary
        +
exact caller-supplied model instance
        |
        v
SimulationModelBinding
        |
        v
SimulationModelBindingCollection
```

`SimulationModelBinding` 保存 exact `component_contract` 与 exact `model`。`component_contract` 必须是既有
PV、Load、Tariff、Battery 或 Grid abstract model boundary；`model` 必须实现该 exact contract。

`SimulationModelBindingCollection` 保存 exact caller tuple、exact binding elements 与 caller order。两个
artifacts 均为 frozen/slotted 且使用 identity-based equality，防止 reconstructed equal-field binding 替代
source identity。

Binding package 依赖既有 component contracts；component contracts 不反向依赖 binding。该层没有 registry、
factory、string lookup、reflection、sorting、deduplication、normalization、selection、model execution、runner、
Runtime、Scheduler、Device、Command、Dispatcher 或 Optimization。

冻结原则：Binding expresses ownership/reference relationship only. It does not execute, select, create or manage
models.

## 13. Single-Step Simulation Execution（TASK-076）

TASK-076 在 binding 之上建立唯一一层单步协调：

```text
SimulationStepInput + SimulationModelBindingCollection
        |
        v
SingleStepSimulationExecutor
        |
        v
SimulationState -> SimulationStepResult
```

执行前完整验证五个 exact component boundary 各有一个 binding；missing 或 duplicate 在任何 model call 前失败。
验证完成后严格遍历 caller tuple，不排序、不重新绑定，每个 model 接收对应 exact component input 并执行一次。

异常语义为 stop-first + exact propagation；没有 retry、fallback 或 partial-result artifact。成功结果复用既有
`SimulationState` 和 `SimulationStepResult`，不创建平行 evidence 模型。

依赖方向：`simulator.executor -> binding + aggregate + component contracts`。Binding、aggregate 与 component
contracts 不反向依赖 executor。该边界没有 scenario、progression、Runtime、Scheduler、Device、Command、
Dispatch、Optimization、cache 或 history。

## 14. Simulation Execution Trace / Evidence（TASK-077）

TASK-077 在单步 executor 之上增加纯观察边界：

```text
completed SimulationStepResult + exact bindings
        |
        v
SimulationExecutionTrace
```

Trace 保存 exact `SimulationStepInput`、`SimulationModelBindingCollection`、`SimulationState` 与
`SimulationStepResult`，并验证：

```text
trace.step_result.simulation_input is trace.simulation_input
trace.step_result.state is trace.state
```

`create()` 不依赖或调用 `SingleStepSimulationExecutor`，也不调用任何 component model。依赖方向保持
`simulator.trace -> aggregate + binding`，executor/aggregate/binding/component contracts 均不反向依赖 trace。

Evidence 语义被限定为 structurally completed：当前 component results 不保存 model identity，因此 trace 只保存
caller 关联的 exact bindings，不宣称能够独立证明 model invocation。该边界没有 replay、progression、Runtime、
Device、Command、persistence、timestamp、UUID、cache 或 history。

## 15. Scenario Execution Boundary（TASK-078）

TASK-078 只组合既有 scenario、single-step executor 与 trace contracts：

```text
SimulationScenario + SimulationModelBindingCollection
        |
        v
ScenarioExecutionBoundary
        |
        +-- SingleStepSimulationExecutor.execute(step, bindings)
        |       exactly once per successful explicit step
        |
        +-- SimulationExecutionTrace.create(bindings, step_result)
        |       exactly once per completed step
        v
ScenarioExecutionResult
```

`ScenarioExecutionBoundary` 无实例状态并使用空 slots。它严格按 `scenario.steps` 的 caller order 执行，不按 sequence
或 timestamp 排序，不去重，也不生成 step。异常立即停止并原样传播，不返回 partial result。

`ScenarioExecutionResult` 是 frozen/slotted、tuple-only artifact，字段为 exact `scenario`、exact `bindings` 和新组装的
trace tuple。它验证：

```text
len(traces) == len(scenario.steps)
traces[index].simulation_input is scenario.steps[index]
traces[index].bindings is bindings
each scenario tuple occurrence has a distinct trace identity
```

因此 result 表达完整、顺序一致的 direct provenance，但不增加 model execution 的证明强度；单步 evidence 语义仍以
TASK-077 为准。

依赖方向保持：`scenario_execution -> executor + trace + aggregate + binding`。既有 component、aggregate、binding、
executor 和 trace contracts 不反向依赖 scenario execution。该边界没有 progression、Runtime、Scheduler、Device、
Command、Dispatch、replay、persistence、retry、cache、history、physics、Optimization 或 EMS strategy。

## 16. Explicit Step Progression Contract（TASK-079）

TASK-079 不实现 progression engine，只定义 caller-owned next-step relationship：

```text
SimulationExecutionTrace + exact previous result
        +
caller-supplied next SimulationStepInput
        |
        v
SimulationStepProgression
```

`SimulationStepProgression` 是 `frozen=True, slots=True, eq=False` 的 identity artifact，保存 exact
`previous_trace`、exact `previous_result` 和 exact `next_input`。核心验证为：

```text
previous_result is previous_trace.step_result
next_input.battery_input.source_state
    is previous_result.state.battery_result.next_state
```

前者防止 reconstructed result 破坏 evidence lineage；后者显式连接 Battery model 已产生的 next state 与 caller 下一
输入的 source state。合同不计算 SOC、不复制或修改 state，也不把其他 component facts 推导为下一步输入。

`SimulationStepProgressionBoundary` 是 abstract、stateless、empty-slotted contract，仅定义
`relate(previous_trace, next_input) -> SimulationStepProgression`，TASK-079 不提供 concrete implementation。

时间完全由 `next_input.step_identity` 的 caller-supplied timestamp/duration 表达。该 package 不导入 datetime/time，
不读取 clock，不增加 sequence/timestamp，不比较 chronology，也不调度或执行下一步。

依赖方向为 `simulator.progression -> trace + aggregate`。Trace、aggregate、executor、scenario execution、Runtime、
Device、Kernel 和策略层不反向依赖 progression。该合同没有 loop、Scheduler、history、persistence、replay、forecast、
Optimization、Constraint evaluation、Command 或 Device integration。

## 17. Phase 7 Integration Validation（TASK-080）

TASK-080 不新增 production boundary，只通过 test-only component models 验证 Phase 7 组合：

```text
Binding -> Scenario Execution -> Single-Step Execution -> Trace -> Progression
```

冻结结果：

- scenario 与 binding order 完全由 caller 控制；
- 每个 component 在每个成功 explicit step 中 exactly once；
- scenario、bindings、steps、traces、step results 与 progression 保持 direct identity；
- 相同 explicit facts 与等价 deterministic models 产生相同 observation values；
- failure stop-first，exact exception propagation，无 retry、skip 或 implicit continuation；
- progression 只验证 caller next input，不生成 step 或推进时间；
- 没有 Runtime、Scheduler、Clock、Thread、Queue、Device、Command、Optimization 或 persistence/history。

TASK-080 仅新增 integration tests 和 Markdown。`simulator/` production code、public API 与既有 tests 均未修改。
完整 Phase 7 报告见 `docs/phase-summary/EOS_Phase7_Deterministic_Simulation_Execution_v1.0.md`。

## 18. Phase 7 Completion Freeze（TASK-081）

TASK-081 将 TASK-075～080 的审查结果冻结为以下架构状态：

```text
caller facts + caller model bindings
        |
        v
deterministic single-step/scenario execution
        |
        v
immutable structural evidence
        +
caller-supplied next step
        |
        v
explicit progression relationship
```

冻结保证：caller 控制 step 与 binding 顺序；完整 binding 在执行前验证；每个成功 step 的每个 component exactly once；
异常 stop-first 并保持 exact exception；result、trace 与 progression 只保存各自合同规定的 exact references。

Identity contract 是直接且局部的。它拒绝 value-equal reconstruction，但不把 trace 描述成 model invocation 的独立证明，
也不宣布未验证的自动跨边界 lineage。

Phase 7 的依赖终点仍是 immutable simulation contracts。它不依赖 Runtime、Scheduler、Clock、Thread、Queue、Device、
Command、Dispatcher、PCS/BMS 或通信协议，也不拥有 EMS strategy、Optimization、Forecast、persistence、history、retry
或 recovery。

TASK-081 只更新 Markdown；Phase 5、Phase 6、`simulator/` production code、public API 与 tests 均保持不变。

## 19. EMS Simulator 1.0 Application Input（TASK-082）

TASK-082 在冻结的 Phase 5～7 之上增加独立应用包 `ems_simulator`，不修改 `decision_formation`、`simulator` 或既有执行边界。

```text
caller-owned 24-hour curves + battery facts + explicit time
        |
        v
ems_simulator.DailySimulationScenarioInput
        |
        v
future application assembly and runner
        |
        v
simulator.SimulationScenario / Phase 7 execution
```

`BatteryParameters` 和 `DailySimulationScenarioInput` 均为 frozen/slotted、无 mutable container 的数据合同。Daily input 保存
exact `step_identities`、PV/Load/Tariff tuples 和 exact battery-parameter reference，并保持 caller order。它要求 24 个 sequence
为 `0..23`、duration 为 3600 秒、timestamp 显式且连续的 hourly facts。

依赖方向为 `ems_simulator -> simulator public contracts`。`simulator` 不依赖应用层。该 input 不依赖 Runtime、Device、Command、
Dispatcher、Optimization 或 Forecast，也不调用 model、executor 或 scenario boundary。

应用输入与 executable `SimulationScenario` 明确分离。TASK-082 不具备 Battery actuation、SOC progression 和 Grid request，因此
不会提前构造完整 `SimulationStepInput`。后续 runner 必须通过显式步骤复用 Phase 5 decision、Phase 6 component contracts 和
Phase 7 executor/trace；不能回写或扩展这些冻结合同。

## 20. Concrete PV Profile Model（TASK-083）

TASK-083 在应用包 `ems_simulator` 中增加 `PVProfileSimulationModel`，实现既有
`simulator.PVSimulationModelBoundary`：

```text
PVSimulationInput.available_power_kw
        |
        v
ems_simulator.PVProfileSimulationModel
        |
        v
PVSimulationResult.actual_power_kw
```

实现是 stateless、empty-slotted，并可作为 exact model instance 绑定到 Phase 7 `SimulationModelBinding`。它每次创建新的
immutable result，但 result 保存 exact input，input 继续保存 exact step identity。相同输入得到相同数值输出，不依赖 cache、
history、clock 或 global state。

profile ownership 仍属于 TASK-082 caller input。未来 application runner 负责把 `pv_power_curve_kw[index]` 显式放入对应
`PVSimulationInput`；model 不保存整条曲线、不按 sequence 查找、不复制或重建输入。

依赖方向保持 `ems_simulator.pv -> simulator public PV contracts`。`simulator` 不反向依赖 concrete model。TASK-083 不修改
Phase 5～7，也不增加 weather/irradiance/temperature、forecast、MPPT、inverter、PCS、Runtime、Device、Command、Strategy
或 Optimization。

## 21. Concrete Load Profile Model（TASK-084）

TASK-084 在 `ems_simulator` 应用层增加 `LoadProfileSimulationModel`，实现既有
`LoadSimulationModelBoundary`：

```text
LoadSimulationInput.demand_power_kw
        |
        v
ems_simulator.LoadProfileSimulationModel
        |
        v
LoadSimulationResult.actual_power_kw
```

model 是 stateless、empty-slotted concrete component，可作为 exact caller model 进入 Phase 7 binding。每次调用产生新
immutable result，且 `result.simulation_input is original_input`，因此 step identity 也沿 input 保持 exact provenance。

profile 仍只由 TASK-082 daily input 持有。future runner 负责逐小时构造 `LoadSimulationInput`；model 不保存 curve、不按
sequence 查找、不复制输入、不读取 clock。

依赖方向为 `ems_simulator.load -> simulator public Load contracts`，无反向依赖。TASK-084 不修改 Phase 5～7，不包含 user
behavior、appliance、stochastic generation、forecast、AI、Runtime、Device、Command、Strategy 或 Optimization。

## 22. Simple Battery Physics Model（TASK-085）

TASK-085 在 `ems_simulator` 应用层增加 frozen/slotted `SimpleBatteryPhysicsModel`，实现既有 Phase 6
`BatterySimulationModelBoundary`：

```text
BatterySimulationInput + exact BatteryParameters
        |
        v
SimpleBatteryPhysicsModel
        |
        v
BatterySimulationResult(actual power, immutable next state)
```

model 保存 exact immutable parameters reference，但不保存 current SOC、step、result、cache 或 history。每次调用只读取 exact
input 中的 source state、actuation 和 duration。Result 保存 exact input，因此 step、state、actuation 与 feasible-decision
provenance 均保持。

能量合同明确：charging stored energy 为 `P * hours * charge_efficiency`；discharging removed energy 为
`|P| * hours / discharge_efficiency`。实际功率受 caller 参数中的 charge/discharge limit、SOC 1.0 与 reserve SOC 限制。
无实际转换时 next state 复用 exact source state；否则创建新 immutable state。

依赖方向为 `ems_simulator.battery -> ems_simulator.input + simulator public contracts`。`simulator` 不依赖 application model。
TASK-085 不修改 Phase 5～7，不引入 SOH、thermal/cell physics、BMS、PCS、CAN、Runtime、Device、Command、Optimization 或
EMS strategy。

## 23. Grid Energy Balance Model（TASK-086）

TASK-086 在 `ems_simulator` 增加 frozen/slotted `GridEnergyBalanceSimulationModel`，实现既有
`GridSimulationModelBoundary`，不修改 Phase 6 Grid input/result：

```text
exact PV result + exact Load result + exact Battery result
        |
        v
GridEnergyBalanceSimulationModel
        + exact same-step GridSimulationInput
        |
        v
GridSimulationResult
```

正式公式为 `grid = load + battery - pv`。Battery positive charging 增加 Grid import；Battery negative discharging 减少
Grid import。Grid positive 表示 import，negative 表示 export。旧草案中的减 Battery 公式被明确拒绝。

model 的三个 result fields 均保持 exact identity，并要求其 `step_identity` 使用 `is` 相同；Grid input 也必须引用同一个 exact
step。Result 保存 exact Grid input。Balance 使用 realized Battery result，不使用可能已被 physics clipping 改变的 actuation
request，也不使用 Grid input 的 requested value 替代 component evidence。

依赖方向为 `ems_simulator.grid -> simulator public contracts`。该 concrete model 是 per-step immutable configuration，不拥有
Runtime state、cache 或 history。Future application runner 负责 component execution ordering；TASK-086 不修改 Phase 5～7、
executor 或 scenario contracts，不引入 Zero Export、strategy、PCS、Device、Command 或 Optimization。

### TASK-087：24 小时 Simulation Runner

`ems_simulator.DailySimulationRunner` 是 Simulator 1.0 的 application orchestration
boundary，不是 Runtime：

```text
DailySimulationScenarioInput
        |
        v
explicit component inputs and simple demo actuation
        |
        v
PV / Load / Battery results
        |
        v
GridEnergyBalanceSimulationModel
        |
        v
SingleStepSimulationExecutor -> SimulationExecutionTrace
        | x 24
        v
DailySimulationResult
```

Runner 是 empty-slotted、stateless execution entry point。它不保存 current SOC、clock、
cache 或 history。时间、step identity 与顺序均来自 exact
`DailySimulationScenarioInput`。`DailySimulationResult` 是 frozen/slotted evidence
aggregate，保存 exact source input、scenario、24 traces 和 23 progressions。

Battery progression 冻结为 `next_step.battery_input.source_state is
previous_trace.state.battery_result.next_state`。Grid 使用 realized Battery result，
继续遵守 `Grid = Load + Battery - PV`。

由于 frozen Phase 7 executor 要求预先提供五个 bindings，而 Grid model 需要同一步已完成
的 component results，runner 先显式协调 PV、Load、Tariff 与 Battery result，再创建
frozen exact-result adapters 和 TASK-086 Grid binding。Adapters 只返回 exact result，
不复制、重建、重算或规范化 evidence。Executor、trace、scenario、progression 以及
Phase 5～7 public contracts 均未修改。

该 boundary 不拥有 Runtime lifecycle、Scheduler、Clock、Device、Command、MPC、
Optimization、Forecast 或 AI。Demo rule 只验证 simulator，不能被视为最终 EMS strategy。

### TASK-088：Simulation Result Output Layer

TASK-088 在 `ems_simulator` 应用层增加只读 output boundary：

```text
exact DailySimulationResult
        |
        v
SimulationResultExporter
        |
        +--> DailySimulationExport.csv_content
        +--> DailyEnergySummary
        `--> SimulationVisualization(power SVG, SOC SVG)
```

Exporter 是 empty-slotted、stateless service。`DailySimulationExport`、
`DailyEnergySummary`、`SimulationVisualization` 和 `SimulationExportPaths` 均为
frozen/slotted artifacts。Summary 与 visualization 必须保持 exact source-result identity。

CSV 固定使用 caller trace order、ISO 8601 timestamp 与 realized PV/Load/Battery/Grid/SOC
values。Summary 使用 exact step duration 把 power 积分为 kWh，并把 Grid positive/negative
分别记录为 import/export positive magnitudes。Visualization 由标准库生成 deterministic
SVG，不依赖 plotting runtime 或 global style state。

`write_files()` 只把已生成的 immutable content 写入 caller-supplied existing directory，
固定命名为 `simulation_result.csv`、`power_curve.svg` 和 `soc_curve.svg`。它不创建
database、dashboard、Web API、cloud storage、Runtime history 或 monitoring path。

依赖方向保持 `ems_simulator.output -> ems_simulator.runner -> simulator contracts`。
Phase 5～7 不反向依赖 output layer，所有既有 contracts 保持不变。

### TASK-089：Simulator 1.0 Demo Composition

`ems_simulator.demo` 是最外层 application composition，不是新的 domain contract：

```text
explicit Demo scenario
        |
        v
existing DailySimulationRunner
        |
        v
existing SimulationResultExporter
        |
        v
caller output directory
```

模块只拥有固定示例 facts 和一次性 orchestration。`DemoExecutionResult` frozen/slotted，并
验证 `simulation_result.source_input is source_input` 与
`export.source_result is simulation_result`。它不修改 runner、exporter、Phase 5～8 contracts
或 simulation evidence。

CLI 可为易用性创建 caller 指定的 output directory，但不保存全局 path、history 或 current
execution。它没有 Runtime lifecycle、Scheduler、background loop、Device、Command、Cloud、
MPC、Optimization、AI 或 Forecast 依赖。Demo rule 是验证夹具，不升级为生产策略边界。

## 24. Phase 9 EMS Strategy Layer Architecture Freeze

Phase 9 在 Simulator 1.0 之外建立正式 EMS Strategy Layer。Simulator 继续负责执行显式
actuation、计算物理状态和记录 evidence；Strategy 只根据事实产生决策请求：

```text
Facts
  |
  v
EMSContext
  |
  v
EMSStrategyBoundary
  |
  v
EMSDecision
  |
  v
Constraint / Feasibility
  |
  v
BatterySimulationActuation
  |
  v
Existing Simulator
```

`EMSContext` 是 frozen/slotted immutable fact snapshot，保存 exact source context、objective
evidence 和 active capability information。它没有 cache、history、Runtime state、clock 或
Device access。Objective 描述业务目标，Capability 描述系统能力，Strategy 根据事实产生请求；
Objective 不直接生成 Intent，Capability descriptor 也不实例化或调用 Strategy。

`EMSStrategyBoundary.evaluate(context) -> EMSDecision` 是 abstract、empty-slotted、stateless
边界。每次 evaluation 只接收一个 Context 并返回一个 Decision，不执行 Constraint、不调用
Simulator、不修改 Context，也不保存历史。

`EMSDecision` 保存 exact `source_context`、exact immutable `source_strategy` descriptor、exact
semantic `intent` 和 requested power。Phase 5 `DecisionIntent` 仍只表达 charge/discharge/idle；
requested power 是非负 raw kW magnitude，方向由 action 表达。显式 post-feasibility handoff
才把它映射为 Simulator signed Battery power。

以下区分被冻结：

```text
EMSDecision != Command
EMSDecision != Feasible Decision
EMSDecision != BatterySimulationActuation
```

Strategy 负责业务目标和决策逻辑；Constraint/Feasibility 负责 SOC、功率、系统能力和物理可行性。
Simulator physics 是最终物理验证，但不替代独立 feasibility boundary。完整 evidence chain 为：

```text
DecisionContext -> EMSContext -> Strategy -> EMSDecision
    -> Feasible Decision -> BatterySimulationActuation -> Simulation Trace
```

每个 boundary 只保证其直接输入与输出之间声明的 identity provenance。禁止 copy、deepcopy、
serialization reconstruction 和 value-only lineage；跨层关系必须由 application composition
显式建立。

Self Consumption、Zero Export 和 TOU 将作为未来 Strategy implementations。MPC 也只能作为
Strategy implementation；其预测和规划数据必须通过独立 caller-supplied immutable horizon
artifact 提供，不得把 solver state、forecast 或 Optimization ownership 塞入基础 `EMSContext`。

Phase 9 不修改 Phase 5～8 contracts，不把 EMS 写入 Simulator，也不引入 Runtime、Scheduler、
Device、Command、Dispatcher 或通信协议。正式决策如何经过 feasibility 并映射为现有
`BatterySimulationActuation`，必须由后续独立 integration boundary 显式定义。

### TASK-090：EMS Core Contracts

TASK-090 首次实现 Phase 9 的三个 immutable artifacts：`EMSStrategyDescriptor`、`EMSContext`
和 `EMSDecision`。它们位于独立 `ems_strategy` package，不属于 `simulator`、`ems_simulator`
或 legacy `kernel/runtime`。

`EMSContext` 保存 exact `DecisionContext`、exact objective/capability composition 和其中一个
exact active `CapabilityDescriptor`。`EMSDecision` 保存 exact context、strategy descriptor 和
Phase 5 semantic `DecisionIntent`，并保存非负 raw kW requested magnitude。TASK-090 不实现
`EMSStrategyBoundary`、Constraint、Actuation handoff 或任何 EMS algorithm。

## 25. Residential Simulation Validation Orchestration

Residential EMS 1.0 functional freeze 后，Campaign C/D 位于 application-level validation/reporting layer，
不属于 production control layer。它们复用同一条冻结 daily chain：

```text
ForecastHorizon -> frozen Strategy / MPC -> EMSDecision
    -> Feasibility -> Actuation -> Simulator actual trace
```

Campaign C 使 caller-owned `ForecastHorizon` 与 caller-owned realized daily facts 分离：前者只进入 planning，
后者只进入 Simulator execution。actual Simulator SOC、grid feedback 与 signed battery power 仍是执行权威；
forecast 不得覆盖 realized facts，也不产生第二条 controller。

Campaign D 是冻结 daily runner 的外层有限 orchestration，而不是 production multi-day EMS runtime。它只用各自
Strategy 上一日完成的 actual Simulator final SOC 作为下一日 initial SOC，故 Schedule/Economic state chains
不交叉；它验证 timezone-aware timestamp 连续性，并在聚合 daily flow accounting 后，仅对整个 horizon 的
final actual SOC 应用一次 terminal energy value。

该层不拥有 Runtime lifecycle、background loop、Command、Device、PCS/BMS、通信、scheduler 或新的 control
capability。它只保留 trace、ledger、KPI、acceptance 与 CSV/SVG/text evidence。Campaign C/D/E 均不构成
hardware timing、restart persistence、field reliability、customer readiness 或 multi-day global optimization 的验证。

### Campaign E keyed synthetic validation layer

Campaign E is a reporting-only outer layer above the frozen Campaign C daily composition. Its keyed sampler creates
immutable caller-owned forecast profiles; realized daily input remains unchanged and continues to feed only Simulator
execution. A sample's Schedule/Economic paths share the exact sampled profile objects, while both are freshly run.
Perfect anchors are separate fresh runs used solely as read-only comparison references. The layer owns sample manifests,
actual-power regret evidence, descriptive statistics and escaped deterministic CSV/SVG reporting; it owns no optimizer,
MPC, physical revision, Feasibility, Actuation, Simulator or runtime behavior.

Its manifest keeps source realized-profile fingerprints, keyed transformation parameters, resulting forecast-profile
SHA-256 fingerprints and a labelled combined forecast fingerprint. Component payloads use caller order, comma
delimiters, fixed-six-decimal normalized evidence values, and canonical `0.000000` for signed zero; they are not raw
Python binary-float hashes and do not enter control or optimization calculations. Reporting deliberately separates the 9,216 sampled
hourly records from 144 hourly records read from the six retained perfect-anchor traces; neither artifact causes a
second execution and anchors never enter sampled ECDF/statistical populations.

Campaign F extends this reporting boundary with keyed correlated core samples, deterministic tail stress cases, and
multi-day evidence aggregation. It does not add control capability: Forecast remains planning input, realized
Simulator facts remain authoritative, and each Strategy path owns its actual SOC carry.

Campaign F selects D01/D03/D02 by exact case ID and fails if a required source is absent; it never falls back to a
generic reference day. Immutable transformed forecast tuples enter the frozen `ForecastHorizon`; separate exact
source realized tuples enter `DailySimulationScenarioInput` and Simulator. The outer layer records keyed correlated
innovations, Cholesky/AR(1) state, clipping and timing shifts, and reads retained daily traces/ledgers for SOC carry,
terminal-once accounting, anchor regret and reporting. Core statistics exclude tails and anchors. This is still only
validation/reporting composition: it adds no Strategy, MPC, optimizer, feasibility, actuation, simulator or runtime
behavior.

Campaign F publication is a four-stage boundary: semantic validation, non-final artifact validation, finalization and
final-artifact validation. Semantic gates verify complete frozen-D signatures including terminal value, exact CRN
scenario/path key multiplicity, exact core/tail membership, and that every retained core/tail/reversal/anchor runner
input still equals its immutable forecast and realized facts. Final artifact validation checks one frozen ordered final
summary schema (including count/metric/gate values and max-evidence references), the actual artifact counts, and every
one of the 882 nested daily CSVs against its completed retained trajectory: 24 rows, timezone-aware hourly sequence,
finite numeric values, semantic action/boolean values and exact row content. It rejects missing, duplicated, reordered
or altered evidence rather than only checking the first record. A final writer exception is a CLI failure; a final
contract failure emits a self-validating FAIL diagnostic with actual rather than normal-topology counts. Final
validation also checks findings content/status, the actual 16 CSV/TXT + 10 SVG + 882 nested decision-file topology,
and every SVG before CLI PASS is emitted. Its maximum metrics are retained argmax sets: value, deterministic plural
references and reference count. Float ties use only reporting tolerance (absolute `1e-9`, relative zero); revision ties
use exact integer equality. The validator parses JSON and recomputes the complete set from raw retained regret/path
evidence with independent maximum/tie/order logic; it shares only frozen constants with generation, so a shared
generator defect cannot certify itself. A single `max()` representative therefore cannot hide a Schedule/Economic tie.
Focused mutation validators inspect one supplied summary or nested CSV, while the production gate retains its complete
882-file scan. Nested regression covers first/middle/last row,
sequence, non-finite, schema and path-traceability failures, including a non-first mutation through real final
orchestration. A final-contract error never leaves PENDING or PASS. CSV accounting evidence
uses fixed 12-decimal fields and a documented `1e-9` reconciliation tolerance. SVGs retain tooltips but also expose
visible short-label mappings and legends: `R/HP/HEL` regimes, `C/T` case classes and `S/E` strategies; ECDFs map
sorted ranks to their actual cases per strategy.

The generator/validator separation is regression-proven with generator-side omission of either strategy, wrong order,
wrong scenario, extra non-maximum reference, wrong count and malformed JSON. All seven targeted validator cases do not
invoke the nested tree validator. Omit Schedule, wrong scenario, extra non-maximum reference, wrong count and malformed
JSON additionally each reach the real final 882-file gate and diagnostic FAIL through production publication orchestration;
the test suite does not synthesize a final finding or publication status.

## 26. Residential EMS 1.0 A–F Unified Validation Layer

Campaign A–F 的统一视角是“冻结控制链之外的验证层”。它将 caller-owned scenario/forecast facts、
已完成的 Simulator actual trace、ledger/comparison/acceptance evidence 和 untracked publication artifacts
组织起来，但不属于 production Runtime：没有 scheduler、device command、后台循环、PCS/BMS 通信或新的
控制决策。

```text
validation orchestration
  ├─ caller-owned forecast facts ──→ frozen planning
  ├─ caller-owned realized facts ──→ frozen Simulator execution
  ├─ retained actual trace ──→ ledger / comparison / acceptance
  └─ retained evidence ──→ publication gate / CSV / SVG / report
```

Simulator actual state（包含完成 step 后的 SOC、grid/battery execution result）是执行事实权威；forecast、
planned request、Campaign evidence 都不能替代它。Campaign E/F 的 synthetic/fixed-seed sampling、CRN、
correlation/Cholesky、AR(1) 与 deterministic tail 都仅属于 validation model：它们不反向改变 Strategy、
MPC、physical revision、Feasibility、Actuation 或 Simulator。

多日 Campaign D/F 也不是新的多日 Runtime：Schedule/Economic 分别携带自己的上一日 actual Simulator SOC，
daily flow 可聚合，而 terminal stock 只以 horizon 最终 actual SOC 计一次。perfect anchor 仅作同环境/同
Strategy 的只读 comparison reference；regret、ranking 和 TIED 都是审查证据，不能被回写为控制目标。

Campaign F 的 fail-closed publication gate 控制的是**证据能否发布**，不是设备使能或安全控制。其四阶段
合同验证 final summary、CSV/SVG topology 和 retained trace 的一致性；失败只产生 diagnostic evidence，绝不
重跑或修改已冻结控制路径。

未来 Edge/PCS/BMS/DSP 集成应在此边界之外建立：云端/Edge planning、嵌入式实时控制、设备通信、telemetry
和 HIL 需要各自的运行与安全合同，再把 actual telemetry 接入同类 ledger/evidence 链。A–F 没有实现或认证
这些硬件层能力。

## 27. Edge P0.5 Feasibility-to-command boundary

P0.5 adds a one-way, stateless adapter at the EMS/Edge boundary:

```text
EMSDecision -> Feasibility -> FeasibleDecision
                              + caller metadata
                                      -> P0.5 PowerCommand
                                      -> P0.6 controlled composition
```

The adapter reads approved action/power only; `ActuationHandoffResult` remains
Simulator-only. It creates no admission, ACK, lifecycle mutation, SOC/actual
fact, clock, transport or execution. `edge_runtime` has no reverse dependency
on `ems_strategy`; P0.5 does not change frozen algorithms or Campaign A–F.
It remains separate from P0.4's current-caller `PowerCommand -> P0.3
admission/safety/runtime -> DeviceTransmissionRequest` adapter-evidence path.
The phase order is P0.3 Controlled Runtime, P0.4 Device Adapter Boundary, P0.5
Command Handoff, then P0.6 controlled composition.

## 28. Edge P0.6 controlled composition evidence boundary

P0.6 composes one caller-owned `FeasibleDecision + EdgeCommandMetadata` through
the frozen P0.5 handoff, one P0.3 controlled-runtime tick, and P0.4 post-tick
adapter audit facts. It returns separate immutable audit evidence, which retains
no live input/runtime/adapter/handoff/request, and a non-serializable current
caller continuation containing only the exact P0.3 next runtime. Historical
evidence cannot recreate a command or resume a cycle.

P0.3 logical execution and reconciliation occur before P0.4 audit facts. An
ACK or adapter actual value cannot replace P0.3 reconciliation or prove physical
completion; `MISSING`/`UNAVAILABLE` facts are explicit audit evidence, not zero
power or success. P0.6 adds no network, protocol, HIL, hardware authority,
scheduler, persistent Runtime, or field control.

## 29. P0.7 controlled composition session（本地候选）

P0.7 在不改变 P0.1–P0.6 的前提下，为 caller 提供同步 session facade。session creation 不执行 cycle；每个
`run_cycle(cycle_input, continuation)` 只调用一次 P0.6 composition。caller 提供 exact approved
`FeasibleDecision`、fresh `EdgeCommandMetadata`、duration 和 tolerance；`PowerCommand` 只在 P0.6 内由
P0.5 生成。success receipt 保留不可执行 audit evidence 与下一 exact one-shot continuation；evidence 不持有
live runtime/adapter/handoff/input/request，continuation 不持有 adapter/handoff 或 command recovery authority，
且 copy、deepcopy、pickle/hydration 均被拒绝。

任何 non-admission、fault、unavailable/malformed adapter fact、ACK/identity mismatch 或 continuation misuse
均 terminal fail-closed；recovery 只能以新 session 和新的 caller facts 开始，绝不 auto-retry/replay。P0.3
reconciliation 与 P0.4 actual telemetry 仍为独立事实层，adapter evidence 不会反向改写 logical execution 或
自证设备完成。此能力是已本地验证、待最终独立复审和发布的候选；不包含 protocol、network、thread、scheduler、
persistence、HIL、PCS/BMS、hardware 或 field control。教学导航见
`docs/learning/RESIDENTIAL_EDGE_P0_6_P0_7_GUIDE.md`。
