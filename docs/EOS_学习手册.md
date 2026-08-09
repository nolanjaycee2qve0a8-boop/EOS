# EOS 学习手册

## 1. 手册定位

本手册面向希望学习 EMS（Energy Management System，能源管理系统）算法、
领域建模与工程架构的开发者。

EOS 不是把所有功能塞进一个控制类的传统 EMS。它首先建立稳定、不可变、可验证的
决策边界，再允许策略、约束、运行时和设备适配能力独立演进。当前阶段的重点是
“EMS 算法未来运行的平台架构”，不是完整的生产控制系统。

后续每完成一个 TASK，都应同步更新本手册中受影响的概念、代码路径和学习建议。

## 2. EMS 系统的整体目标

EMS 需要在物理设备能力、实时观测、外部经济信息和安全约束之间做出可解释的能源
决策。典型系统包含以下对象：

| 对象 | 物理含义 | EMS 关注的信息 | EOS 当前对应边界 |
| --- | --- | --- | --- |
| PV | 光伏发电系统 | 可用功率、实际功率 | `PVState`、`DecisionContext.pv_power_kw` |
| Battery | 储能电池 | SOC、SOH、容量、可充放功率 | `BatteryState`、`DecisionContext` |
| PCS | 储能变流器 | 有功、无功、运行和故障状态 | `PCSState` |
| Load | 用电负荷 | 当前消费功率 | `DecisionContext.load_power_kw` |
| Grid | 公共电网 | 进出口功率、电压、频率 | `GridState`、`DecisionContext.grid_power_kw` |
| Electricity Price | 电价信号 | CNY/kWh，允许有符号价格 | `electricity_price_cny_per_kwh` |

这些信息不是一回事：

- 设备定义描述“它是什么、能力是多少”；
- 系统状态描述“现在观测到什么”；
- 决策上下文描述“本次决策能看到哪些事实与约束”；
- 策略描述“希望系统做什么”；
- 约束判断“这个意图是否可行”；
- 执行层负责“如何把可行意图变成外部动作”。

## 3. EMS 的核心问题

### 3.1 自发自用

目标是优先在本地消纳 PV：

- PV 大于负荷时，剩余能量可用于充电；
- 负荷大于 PV 时，电池可尝试放电以减少电网购电；
- 实际能否充放电仍要经过 SOC、功率和设备能力约束。

策略只表达意图，不能绕过约束或直接控制 PCS。

#### TASK-037 SelfConsumptionPolicy

TASK-037 已实现第一个最小策略 `SelfConsumptionPolicy`。它只比较当前
`pv_power_kw` 与 `load_power_kw`：

- PV 剩余时产生正值充电意图；
- 负荷缺口时产生负值放电意图；
- 两者平衡时产生零值空闲意图。

该实现刻意不读取 SOC、reserve SOC 或电池功率限制，也不产生设备命令。这不是遗漏，
而是用于保持 Policy 与 Constraint、Execution 的职责分离。

**目标**

实现第一个具体 EMS 策略，验证实际能源管理逻辑可以接入 TASK-001～036 建立的决策
基础设施。

**输入与使用字段**

- 输入：`DecisionContext`
- 使用：`pv_power_kw`
- 使用：`load_power_kw`

**输出**

`DecisionContextResult` 中保存策略创建的 exact `DecisionIntent`。

**意图语义**

- `battery_power_intent_kw > 0`：充电意图；
- `battery_power_intent_kw < 0`：放电意图；
- `battery_power_intent_kw == 0`：空闲意图。

**明确排除**

- SOC 限制；
- 电池功率限制；
- PCS 控制；
- 设备命令；
- runtime 执行。

排除这些职责的原因是保持 Policy 与 Constraint、Execution 的边界稳定。

### 3.2 峰谷套利

目标是在低价时储能、高价时释放能量。它需要：

- 明确的电价单位与时间语义；
- 电池容量和功率约束；
- 对未来时段的规划；
- 对收益、效率和寿命成本的权衡。

TASK-046 已提供第一个显式、规则型 TOU Capability：它依据 caller-supplied 小时、
价格阈值和意图功率生成 `DecisionIntent`。它不是调度器或优化器，也不规划未来时段、
收益、效率或寿命成本。

### 3.3 防逆流

目标是限制或禁止向电网反送电。工程上必须统一电网功率符号：

- `grid_power_kw > 0`：从电网进口；
- `grid_power_kw < 0`：向电网出口；
- `grid_power_kw == 0`：平衡。

防逆流不能只靠策略意图完成，还需要约束、实时执行和设备反馈闭环。

### 3.4 削峰填谷

目标是在负荷峰值时放电、低谷时充电，从而控制需量或改善负荷曲线。它通常需要：

- 峰值定义与统计窗口；
- 可用能量和功率限制；
- 时间计划或预测；
- 失败与降级处理。

这些能力不属于当前基础边界，未来应作为独立策略与能力模块引入。

### 3.5 电池寿命优化

目标是在经济收益和电池退化之间取得平衡。可能涉及：

- SOC 工作区间；
- 循环深度与吞吐量；
- 温度、SOH 和倍率；
- 退化成本模型。

EOS 当前状态模型只提供事实，不包含退化推导。寿命模型、优化目标和策略必须保持
独立，不能隐藏在状态对象或通用运行时中。

## 4. EOS 决策链

当前面向未来 EMS 算法的主链如下：

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
DecisionContextResult
        |
        v
DecisionIntent
        |
        v
DecisionConstraintBoundary
        |
        v
FeasibleDecisionIntent
        |
        v
ConstraintExplanation
        |
        v
DecisionEvaluationCycle
        |
        v
DecisionEvaluationOrchestrator
```

### 4.1 EnergySystemState

**为什么存在**

物理系统的观测不应散落在函数参数、字典或设备协议对象中。统一的系统状态可以明确
记录电池、PCS、PV 和电网在同一观察边界上的事实。

**解决什么工程问题**

- 分离物理事实与 EMS 决策；
- 统一单位、范围和功率方向；
- 避免运行时或策略直接依赖设备通信模型。

**输入**

已经验证的 `BatteryState`、`PCSState`、`PVState` 和 `GridState`。

**输出**

不可变的 `EnergySystemState` 聚合对象，并保持四个组件的原始对象身份。

**为什么不能与其他模块合并**

状态不应包含价格、策略、命令或执行结果。若与 `DecisionContext` 合并，外部经济事实
和策略约束会污染物理观测；若与 policy 合并，状态对象将拥有决策行为。

### 4.2 DecisionContextAssembler

**为什么存在**

物理状态不是完整的决策输入。时间、电价、负荷、容量和策略约束可能来自其他可信
来源，因此需要显式装配边界。

**解决什么工程问题**

- 明确哪些字段来自物理状态；
- 强制外部决策事实由调用者逐项提供；
- 防止默认值和隐藏推导进入决策。

**输入**

`EnergySystemState`，以及 keyword-only 的时间、功率限制、容量、负荷、电价、
保留 SOC 和出口限制。

**输出**

一个新的、不可变的 `DecisionContext`。

**为什么不能与其他模块合并**

Assembler 只做映射。若与 policy 合并，策略会同时负责采集与决策；若与 state 合并，
物理观测会被外部经济信息污染。

### 4.3 DecisionContext

**为什么存在**

策略需要一个稳定、完整且可重复测试的输入快照，而不是许多松散参数。

**解决什么工程问题**

- 固化决策时刻所见事实；
- 明确字段单位、数值范围和符号；
- 为测试、解释和未来重放提供确定输入。

**输入**

Assembler 提供的显式事实。

**输出**

不可变决策输入对象；它本身不执行任何计算或策略。

**为什么不能与其他模块合并**

Context 是事实，Result 是输出，Policy 是行为。合并后会产生可变的“大上下文”，
破坏输入输出边界和可测试性。

### 4.4 DecisionContextPolicy

**为什么存在**

不同 EMS 算法必须共享稳定的调用合同。

**解决什么工程问题**

- 允许策略替换；
- 规定唯一输入是 `DecisionContext`；
- 规定唯一输出是 `DecisionContextResult`；
- 隔离算法与 runtime、dispatcher 和设备。

**输入**

一个不可变 `DecisionContext`。

**输出**

一个 `DecisionContextResult`。

**为什么不能与其他模块合并**

若与 runtime 合并，算法会拥有时钟、循环或状态；若与 constraint 合并，策略意图和
物理可行性将无法独立审查；若与 device 合并，语义决策会退化为协议命令。

### 4.5 DecisionIntent

**为什么存在**

策略输出首先是业务语义，而不是设备指令。

**解决什么工程问题**

- 表达“希望电池以多少功率充放电”；
- 统一单位与方向；
- 为约束层提供不可变输入。

**输入**

策略计算得到的 `battery_power_intent_kw`。

**输出**

不可变意图。当前约定为：

- 正值：充电；
- 负值：放电；
- 零：空闲；
- 数值是未经缩放的 kW。

**为什么不能与其他模块合并**

Intent 不是 command，也不是 constraint result。与命令合并会绑定 PCS/BMS 协议；
与 feasible result 合并会掩盖策略原始意图。

### 4.6 DecisionConstraintBoundary

**为什么存在**

策略表达“想做什么”，约束层负责判断“能不能做”。这两个问题必须独立。

**解决什么工程问题**

- 为 SOC、功率、出口等未来约束预留稳定接口；
- 避免策略内隐藏 clipping 或安全逻辑；
- 允许约束实现独立测试和替换。

**输入**

原始 `DecisionIntent`。

**输出**

`FeasibleDecisionIntent`。

**为什么不能与其他模块合并**

与 policy 合并会让策略同时承担偏好和安全责任；与 runtime 合并会让执行层重新解释
业务规则。Phase 1 先建立通用接口，TASK-038 再在不改变接口的前提下加入第一个具体
电池约束实现。

### 4.7 Battery Constraint Layer

TASK-038 Battery Constraint Implementation 是 EOS 第一个具体物理约束实现。
TASK-001～037 建立决策基础设施，TASK-037 的 Policy 首次产生真实能源管理意图；
TASK-038 的 Constraint 首次根据电池物理限制把策略意图转换为可行意图。

```text
DecisionIntent
        |
        v
BatteryConstraintImplementation
        |
        v
FeasibleDecisionIntent
```

**Intent 与 Capability 的区别**

- Intent：策略希望做什么；
- Constraint：系统的物理能力允许做什么。

Policy 根据能源状态产生意图，不负责 SOC 限制、电池功率限制或设备能力判断。
Constraint 只负责将已有意图限制在物理可行范围，不重新制定策略。

**输入**

原始 `DecisionIntent`。

**约束事实**

`BatteryConstraintImplementation` 在构造阶段接收一次评估所需的 immutable battery
facts：

- `soc`：`[0, 1]` 的无量纲比例；
- `reserve_soc`：`[0, 1]` 的无量纲比例；
- `max_charge_power_kw`：非负、未经缩放的 kW；
- `max_discharge_power_kw`：非负、未经缩放的 kW。

**输出**

`FeasibleDecisionIntent`。

**核心规则**

- SOC 达到满电限制时禁止继续充电；
- SOC 小于或等于 `reserve_soc` 时禁止继续放电；
- 超过最大充放电功率时限制到对应最大值；
- 未调整时保持原始 intent identity；
- 禁止或裁剪时生成新的 immutable intent，不修改原始 `DecisionIntent`。

**为什么不能与其他模块合并**

与 Policy 合并会让策略同时承担意图生成和物理可行性判断；与 Runtime 或 Device
合并会让约束依赖执行机制。保持独立边界后，策略与约束可以分别替换和测试。

**刻意不包含**

- PCS 或 BMS 控制；
- CAN、Modbus 或 device command；
- runtime 执行或 dispatch；
- optimization 或 forecasting；
- SOC 计算、history、cache 或 mutable runtime state。

### 4.8 Grid Constraint Boundary

TASK-040 建立并网侧物理约束的抽象入口，但不实现任何限制算法。

```text
source DecisionIntent
        |
        v
GridConstraintBoundary
        |
        v
FeasibleDecisionIntent
```

**为什么存在**

电池能力与并网能力是不同的物理责任。电池约束关注 SOC 和充放电能力；并网约束未来
可能关注进口功率、出口功率和 zero-export capability。它们不应被塞入同一个具体类。

**解决什么工程问题**

- 为未来 grid import/export constraints 提供稳定扩展点；
- 保持通用 `DecisionConstraintBoundary.evaluate(intent)` 契约不变；
- 防止 grid-specific facts 泄漏到 Policy、Orchestrator 或通用约束接口。

**输入**

已有的 immutable `DecisionIntent`。

**输出**

`FeasibleDecisionIntent`。

**为什么不能与其他模块合并**

与 Policy 合并会让策略承担并网物理可行性；与 Battery Constraint 合并会混淆电池和
并网点的能力所有权；与 Runtime、PCS 或 device adapter 合并会把约束判断绑定到执行。

TASK-040 的 boundary 不保存 grid import limit、grid export limit 或 zero-export flag。
未来具体实现可以通过构造阶段接收明确定义的 immutable grid facts，但必须继续保持
通用 `evaluate(intent)` 签名。

**刻意不包含**

- grid import/export limit 算法；
- zero-export 或防逆流算法；
- TOU、电价策略、optimization 或 forecasting；
- PCS 控制、device command、dispatch 或 runtime；
- cache、history、persistence 或 telemetry。

### 4.9 Grid Power Limit Constraint

TASK-041 是第一个具体 Grid Constraint 实现。它不把 battery intent 当成 grid power，
而是显式接收“应用本次 battery intent 前”的并网基准功率。

```text
source DecisionIntent
        |
        v
GridPowerLimitConstraintImplementation
        |
        v
FeasibleDecisionIntent
```

**输入**

`DecisionIntent`，其中 `battery_power_intent_kw` 继续保持：

- 正值：电池充电；
- 负值：电池放电；
- 零：空闲。

**约束事实**

- `grid_power_baseline_kw`：应用本次 battery intent 前的并网功率，正值进口、负值
  出口；
- `max_import_power_kw`：非负进口功率上限；
- `max_export_power_kw`：非负出口功率幅值上限。

所有值均为未经缩放的 kW。允许的并网区间是：

```text
[-max_export_power_kw, max_import_power_kw]
```

**确定性计算**

```python
projected_grid_power_kw = grid_power_baseline_kw + battery_power_intent_kw
```

Constraint 将 projected grid power 限制在允许区间，再反推出允许的 battery intent。
它不进行预测、电价分析或设备控制。

**Identity**

- 无需调整时保留 exact source intent identity；
- 发生限制时创建新的 immutable `DecisionIntent`；
- 原始 Policy intent 永不修改。

**为什么不能与其他模块合并**

与 Policy 合并会让策略承担并网物理限制；与 `DecisionIntent` 合并会混淆 battery power
和 grid power；与 Runtime/Device 合并会让约束读取或控制外部状态。

**刻意不包含**

- 专用 Zero Export 策略或控制器；
- TOU、电价、optimization、forecasting 或 scheduling；
- PCS/BMS 控制、command、dispatch 或 runtime；
- persistence、telemetry、cache 或 history。

### 4.10 Constraint Evaluation Pipeline

TASK-042 定义多个 Constraint 如何按明确顺序组合，但不选择约束、排序约束或实现新的
物理算法。

```text
source DecisionIntent
        |
        v
ConstraintEvaluationPipeline
        |
        +--> Battery Constraint
        |
        +--> Grid Constraint
        |
        v
final FeasibleDecisionIntent
```

**为什么存在**

一个真实意图可能需要同时满足电池能力与并网能力。如果调用顺序散落在 Policy、
Runtime 或应用代码中，同一组约束可能产生不同生命周期。

**输入**

- exact source `DecisionIntent`；
- caller supplied `tuple[DecisionConstraintBoundary, ...]`。

Tuple 位置就是完整顺序。Pipeline 不排序、不去重、不并行执行。

**输出**

最后一个 constraint 返回的 exact `FeasibleDecisionIntent`。每个 constraint 接收上一
阶段返回 wrapper 中的 exact inner intent。

若 tuple 为空，Pipeline 返回一个引用 exact source intent 的
`FeasibleDecisionIntent`。

**Identity**

- source intent 不复制、不修改；
- 每一阶段保留上一阶段输出对象身份；
- 最终 wrapper 不重建；
- 所有 constraint 都不调整时，最终 inner intent 仍是 source intent。

**为什么不能与其他模块合并**

与 Policy 合并会让策略知道物理约束顺序；与 Runtime 合并会让执行层重新解释可行性；
让 Pipeline 保存 constraint 列表则会引入运行时所有权和可变顺序。

**刻意不包含**

- constraint priority、排序或冲突解决算法；
- optimization、MPC、forecast、TOU 或 pricing；
- async、parallel、retry、rollback 或 partial result；
- runtime、command、dispatch、PCS/BMS 或 device control；
- persistence、telemetry、cache 或 history。

### 4.11 FeasibleDecisionIntent

**为什么存在**

需要一个明确对象表示“某个原始意图已经通过某个约束边界”。

**解决什么工程问题**

- 保存约束允许执行的 effective `DecisionIntent` 身份；
- 区分原始策略输出和约束阶段产物；
- 为后续命令生成提供明确输入类型。

**输入**

通过约束边界的 `DecisionIntent`。

**输出**

包含 exact feasible intent 引用的不可变 wrapper。若约束未调整，inner intent 与
policy source intent 是同一对象；若发生阻止或裁剪，则 inner intent 是新的
immutable 对象。

**为什么不能与其他模块合并**

若直接覆盖原始 intent，就无法审计策略到底产生了什么；若与 command 合并，就跨越了
语义决策与设备执行边界。

### 4.12 ConstraintExplanation

**为什么存在**

完成的约束阶段需要可观察的关系证据，但不应在观察层重新推理。

**解决什么工程问题**

- 关联 feasible intent 与 source intent；
- 用对象身份验证生命周期链；
- 为未来展示或审计提供稳定入口。

**输入**

已有的 `FeasibleDecisionIntent` 和 policy 原始 `source_intent`。

**输出**

保存 exact feasible/source references 的不可变观察对象。

**为什么不能与其他模块合并**

Explanation 不执行约束，也不生成理由或推荐。与约束算法合并会让观察触发计算；
与持久化合并会让领域对象承担存储职责。

### 4.13 Constraint Explanation Chain

TASK-043 在既有单阶段关系观察之外，增加多 Constraint 的有序解释证据。

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

**为什么存在**

最终 feasible intent 只能说明“最后允许什么”，不能单独说明每个 Constraint 是否调整
了输入，以及调用者为该调整提供了什么原因。Chain 将每一阶段的完成证据按原顺序保存。

**输入**

- exact chain source `DecisionIntent`；
- caller-supplied `tuple[ConstraintExplanationEntry, ...]`；
- exact final `FeasibleDecisionIntent`。

每个 Entry 保存 exact stage source、exact stage feasible、`adjusted` 和
`adjustment_reason`。`adjusted` 由对象 identity 定义，而不是数值相等：

```python
adjusted = feasible_intent.intent is not source_intent
```

**输出**

一个 frozen、slotted `ConstraintExplanationChain`。它保存 exact tuple 顺序，并验证
下一 Entry 的 source 是上一 Entry 的 exact feasible inner intent。

**Reason 的边界**

Reason 是调用者显式提供的 opaque evidence。Chain 不读取 SOC、功率限制、电网状态或
价格来推导原因，也不生成推荐、诊断或新结论。未调整时 reason 必须为 `None`；调整时
必须提供非空字符串。

**为什么不能与其他模块合并**

修改既有 `ConstraintExplanation` 会破坏 TASK-033 和
`DecisionEvaluationCycle` 的稳定契约；让 Constraint 返回 reason 会改变通用
`DecisionConstraintBoundary`；在 Pipeline 中推导 reason 会让执行与观察混合。

**刻意不包含**

- constraint 执行、选择、排序、priority 或冲突解决；
- TOU、pricing、optimization、MPC 或 forecasting；
- runtime、command、dispatch、PCS/BMS 或 device control；
- persistence、telemetry、logging、cache 或 history。

### 4.14 DecisionEvaluationCycle

**为什么存在**

一次完成的决策评估包含 context、result、source intent、feasible intent 和
explanation。需要一个统一生命周期对象验证这些产物确实属于同一次 lineage。

**解决什么工程问题**

- 保存一次完整评估的证据；
- 通过 `is` 分别校验 source 与 feasible 关系；
- 防止来自不同评估的对象被误拼接。

**输入**

已经完成的决策产物，不接收 policy 或 constraint 实例。

**输出**

不可变 `DecisionEvaluationCycle`。

其关键合同是：

```python
cycle.source_intent is cycle.result.intent
cycle.explanation.source_intent is cycle.source_intent
cycle.explanation.feasible_intent is cycle.feasible_intent
```

约束未调整时：

```python
cycle.feasible_intent.intent is cycle.source_intent
```

约束阻止或裁剪时：

```python
cycle.feasible_intent.intent is not cycle.source_intent
```

**为什么不能与其他模块合并**

Cycle 是结果边界，不是执行器。让它调用 policy 或 constraint 会使对象构造产生副作用，
也会失去“已完成生命周期观察”的语义。

### 4.15 DecisionEvaluationOrchestrator

**为什么存在**

调用者不应重复手工拼接 assembler、policy、constraint、explanation 和 cycle。

**解决什么工程问题**

- 固定一次评估的调用顺序；
- 确保每个既有边界只调用一次；
- 保持中间产物的 exact identity；
- 统一失败传播。

**输入**

调用者提供的 `EnergySystemState`、`DecisionContextPolicy`、
`DecisionConstraintBoundary` 和全部外部决策事实。

**输出**

一个完整的 `DecisionEvaluationCycle`。

**为什么不能与其他模块合并**

Orchestrator 只协调，不拥有 policy、constraint、runtime 或 device。若与 policy 合并，
算法会控制生命周期；若与 runtime 合并，新决策路径会被隐式接入旧执行路径。

TASK-039 修复后，Orchestrator 会把 policy 的 exact source intent 和 constraint 的
exact feasible output 同时传入 explanation/cycle，不复制或重建任一对象。

### 4.16 DecisionEvaluationIntegration

TASK-044 建立新决策路径的一次完整评估入口。

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

**为什么存在**

Assembler、Policy、Pipeline、Explanation Chain 和 Cycle 都是独立边界。若由每个
调用者自行拼接，容易重复执行 Constraint、丢失中间 identity 或让 reason 来源不一致。

**输入**

- caller-supplied `EnergySystemState` 与 `DecisionContextPolicy`；
- caller-supplied constraint tuple；
- 与 constraint 按索引对应的 adjustment reason tuple；
- DecisionContext 所需全部显式外部 facts。

**输出**

一个 frozen/slotted `DecisionEvaluationIntegrationResult`，其中保存：

- exact `DecisionEvaluationCycle`；
- exact `ConstraintExplanationChain`。

Result 验证 Chain 与 Cycle 共享 exact source intent 和 exact final feasible wrapper。

**Exactly once**

Integration 只调用一次 `ConstraintEvaluationPipeline`。每个底层 Constraint 在该次
Pipeline 调用中只执行一次。每个完成阶段的 exact input/output 同时形成 immutable
Explanation Entry，不重跑 Constraint。

**Reason ownership**

调用者为每个 Constraint 提供“发生调整时使用的 reason”。Identity 未变化时 Entry
记录 `None`；发生变化时记录 caller 原始字符串。Integration 不分析 SOC、Grid 或价格
来生成 reason。

**为什么不能与其他模块合并**

修改 Pipeline 以返回中间值会破坏 TASK-042；修改 Cycle 保存 Chain 会破坏 TASK-034；
修改旧 Orchestrator 会迁移已接受的单 Constraint 路径。因此 TASK-044 使用独立集成
边界，并保持旧 Orchestrator 并存。

**刻意不包含**

- EMS strategy、constraint algorithm、optimization、MPC 或 forecast；
- TOU、pricing 或 scheduling；
- runtime、command、dispatch、PCS/BMS 或 device control；
- persistence、telemetry、cache、history、retry 或 rollback。

### 4.17 EMSCapabilityBoundary

TASK-045 建立 Phase 3 EMS Capability Layer 的第一个抽象扩展入口。

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

**为什么存在**

Policy、Constraint 和 Integration 已经形成稳定合同，但未来自发自用、峰值管理、TOU
等业务能力仍需要独立演进。如果业务目标直接进入 Constraint，会混淆“希望做什么”和
“物理上允许什么”；如果进入 Runtime 或 Device，会把语义意图与执行绑定。

**输入**

一个 exact、immutable `DecisionContext`。它包含本次决策可见的物理观测、外部事实和
显式约束输入。

**输出**

一个 `DecisionIntent`。TASK-045 只定义返回类型和扩展位置，不实现任何具体 EMS
算法。

**与 Policy 的关系**

现有 `DecisionContextPolicy.evaluate(context) -> DecisionContextResult` 保持不变。
`EMSCapabilityBoundary` 不继承 Policy，不包装 Policy，也没有被
`DecisionEvaluationIntegration` 自动调用。未来如何组合必须通过独立 TASK 和 ADR
明确决定。

**Stateless contract**

边界是 abstract、empty-slotted，并且没有 `__dict__`、cache、history 或 runtime
state。它不保存 Policy、Constraint、Dispatcher 或 Device 实例。

**为什么不能与其他模块合并**

- 与 Policy 合并会在 TASK-045 中隐式迁移已接受的 Policy contract；
- 与 Constraint 合并会让业务目标负责 SOC、功率或 Grid 可行性；
- 与 Runtime/Device 合并会让能力层拥有生命周期或控制责任；
- 与 `DecisionContext` 合并会让不可变事实对象拥有行为。

**刻意不包含**

- 具体 EMS capability 或 strategy；
- SOC、功率、Grid limit 或 Constraint 执行；
- optimization、MPC、forecast、TOU 或 pricing；
- runtime、command、dispatch、PCS/BMS 或 device control；
- persistence、telemetry、cache、history 或 scheduling。

### 4.18 TOUEnergyCapability

TASK-046 在 Phase 3 边界上实现第一个具体 EMS Capability。

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

**为什么存在**

TOU 业务目标需要把当前时刻与电价事实转换为充电、放电或空闲意图。该逻辑属于“希望
系统做什么”，不是电池或电网物理可行性，也不是设备执行。

**输入**

- exact immutable `DecisionContext`；
- frozen/slotted `TOUCapabilityParameters`。

参数显式包含：

- `charge_hours`、`discharge_hours`：context timestamp 时区内的 0～23 本地小时 tuple；
- `charge_price_ceiling_cny_per_kwh`：充电价格上限，raw CNY/kWh；
- `discharge_price_floor_cny_per_kwh`：放电价格下限，raw CNY/kWh；
- `charge_power_intent_kw`、`discharge_power_intent_kw`：非负 raw kW 意图幅值。

充电与放电小时不得重叠。Capability 不读取系统时钟，不查 tariff database，也不执行
时区转换。

**输出**

一个新 immutable `DecisionIntent`：

- 处于充电小时且价格不高于 charge ceiling：输出正充电意图；
- 处于放电小时且价格不低于 discharge floor：输出负放电意图；
- 其他情况：输出零意图。

阈值比较包含等号。没有默认 tariff、隐藏缩放或自动 schedule。

**Capability 与 Constraint**

TOU Capability 产生偏好，不检查 SOC、reserve SOC、电池充放电能力或 Grid limit。
这些意图仍必须进入既有 Constraint 层才能成为 `FeasibleDecisionIntent`。

**为什么不能与其他模块合并**

- 与 Constraint 合并会把价格偏好误当成物理安全；
- 与 Policy 合并会修改已接受的 Policy contract；
- 与 Runtime 合并会让规则依赖时钟、调度或状态；
- 与 Device 合并会把 kW 意图变成 PCS/BMS 命令。

**刻意不包含**

- tariff lookup、calendar、minute-level schedule 或时区转换；
- optimization、MPC、forecast 或收益规划；
- SOC、电池功率或 Grid Constraint；
- peak shaving、zero export 或 pricing recommendation；
- runtime、command、dispatch、PCS/BMS 或 device control；
- persistence、telemetry、cache 或 history。

### 4.19 CapabilityCompositionBoundary

TASK-047 建立多个 EMS Capability 的抽象组合边界。

```text
DecisionContext
        +
caller-ordered capability tuple
        |
        v
CapabilityCompositionBoundary
        |
        v
tuple[DecisionIntent, ...]
```

**为什么存在**

未来一个 DecisionContext 可能需要由多个业务 Capability 同时观察。直接让调用者自由
拼接会导致执行次数、顺序、异常传播和身份保持不一致；但现在把多个 intent 合成一个
结果，又会提前发明 priority 或 conflict resolution 规则。

**输入**

- exact immutable `DecisionContext`；
- caller-supplied `tuple[EMSCapabilityBoundary, ...]`。

Tuple 位置就是权威顺序。重复出现同一个 Capability 表示两个调用位置，不能自动去重。

**输出**

`tuple[DecisionIntent, ...]`，与输入 capability tuple 一一对应。每个元素是对应
Capability 返回的 exact intent reference。

**Exactly once**

一个符合合同的实现必须让每个 tuple 位置执行 exactly once，并把同一个 exact context
传给每次调用。Capability 失败时立即停止，原异常向上传播，后续位置不执行。

**为什么不返回一个 DecisionIntent**

选择、相加、平均、裁剪或评分都属于新的业务决策。TASK-047 没有这些权限，因此只保留
有序输出，不进行 resolution。未来 resolution 必须由独立 TASK 与 ADR 定义。

**Stateless boundary**

生产代码只新增 abstract、empty-slotted boundary，不新增 concrete composition
pipeline。边界不保存 capability、context、intent、cache、history 或 runtime state。

**刻意不包含**

- capability selection、priority、scoring、arbitration 或 conflict resolution；
- TOU、自发自用、peak shaving、SOC 或 Grid 业务逻辑；
- optimization、MPC、forecast 或 scheduling；
- Constraint 执行、Explanation 或 Evaluation Integration；
- runtime、command、dispatch、PCS/BMS 或 device control；
- persistence、telemetry、cache 或 history。

### 4.20 IntentResolutionBoundary

TASK-048 在 capability candidates 与 Constraint 之间建立 intent resolution 的抽象扩展
入口。

```text
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

**为什么存在**

Capability Composition 可以确定性地产生多个独立 intent，但 Constraint 接收的是一个
source intent。如果让 Composition 直接选出结果，就会破坏“执行多个能力”与“处理业务
冲突”的职责分离；如果让 Constraint 选择，则会让物理可行性层决定业务目标。

**输入**

`tuple[DecisionIntent, ...]`。Tuple 是已有 candidate artifacts 的 immutable 容器。
Resolution boundary 不重新执行 Capability，不修改 candidate，也不保存候选历史。

**输出**

一个 `DecisionIntent`，作为未来进入 Constraint 层的 source intent。

TASK-048 只固定类型边界，不决定输出是否必须是某个 exact candidate，也不授权构造新的
intent。空 tuple、冲突 candidates、identity 和失败语义必须由未来具体 resolver 的独立
TASK 与 ADR 明确。

**为什么不能与 Composition 合并**

Composition 回答“哪些 Capability 被调用、以什么顺序产生了哪些独立结果”。Resolution
未来回答“多个业务候选如何得到一个结果”。前者是确定性执行合同，后者需要业务规则；
合并两者会隐藏 priority、selection 或 arbitration。

**Stateless boundary**

生产代码只新增 abstract、empty-slotted boundary。它不保存 candidates、resolved
intent、cache、history 或 runtime state，也没有 concrete production resolver。

**刻意不包含**

- priority、weight、score、ranking 或 automatic selection；
- averaging、summation、intent merging 或 conflict arbitration；
- optimization、MPC、forecast、scheduling 或 AI selection；
- TOU、SOC、Battery、Grid、PCS/BMS 或 device logic；
- Constraint 执行、Evaluation Integration、Runtime 或 Dispatch；
- persistence、telemetry、cache 或 history。

### 4.21 SelfConsumptionCapability

TASK-049 新增第二个具体 EMS Capability，用当前 PV 与 Load 事实产生一个独立的
self-consumption candidate intent。

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
Future Resolution / Constraint
```

**为什么存在**

TOU Capability 表达时间与价格目标；Self Consumption Capability 表达“优先使用当前
PV 覆盖当前 Load”的业务目标。它们应当分别产生 candidate intents，未来再由独立
resolution 层处理多个目标，而不是让一个 Capability 知道另一个 Capability。

**输入**

只读取：

- `pv_power_kw`：当前 PV 发电功率，raw kW；
- `load_power_kw`：当前负载功率，raw kW。

它不读取 timestamp、price、SOC、reserve SOC、battery limit、grid power 或 export
limit。

**输出与符号**

```text
battery_power_intent_kw = pv_power_kw - load_power_kw
```

- PV surplus：结果大于零，表示电池充电意图；
- PV deficit：结果小于零，表示电池放电意图；
- balanced：结果为零，表示空闲意图。

没有单位转换、隐藏缩放、裁剪、饱和或 rounding。

**为什么不能与 Constraint 合并**

Capability 表达希望吸收全部 PV surplus 或补足全部 Load deficit。即使 SOC 已满、
reserve SOC 已触发或 power limit 为零，它仍返回完整原始意图；Battery/Grid Constraint
随后决定物理上允许多少。

**与 SelfConsumptionPolicy 的关系**

TASK-037 的 `SelfConsumptionPolicy` 属于独立 Policy contract，并返回
`DecisionContextResult`。TASK-049 的 `SelfConsumptionCapability` 属于 Capability
contract，直接返回 `DecisionIntent`。两者不继承、不调用、不适配、不迁移，也不共享
mutable state。

**Stateless**

该 Capability fieldless、empty-slotted，不保存 context、intent、cache、history 或
runtime state。

**刻意不包含**

- SOC、reserve SOC 或 battery power limit；
- Grid limit、export limit 或 zero-export；
- TOU、pricing、optimization、MPC 或 forecast；
- Resolution、Constraint 或 Evaluation 执行；
- Runtime、Dispatch、PCS/BMS、communication 或 device control；
- persistence、telemetry、cache 或 history。

### 4.22 DeterministicIntentResolutionImplementation

TASK-050 实现第一个具体、可替换 Intent Resolver。它用 caller 显式注入的 immutable
tuple index，从多个 candidate intents 中返回一个 exact intent。

```text
tuple[DecisionIntent, ...]
        +
selected_candidate_index
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

**为什么存在**

TASK-048 只定义 candidates 到单一 intent 的抽象入口。TASK-050 证明这个入口可以拥有
具体实现，同时仍不依赖 capability 名称、SOC、Grid 或 Runtime。

**Immutable parameters**

`DeterministicIntentResolutionParameters` 只包含
`selected_candidate_index`：

- unitless、零基整数；
- 必须大于或等于零；
- 没有默认值；
- 调用 `resolve()` 时必须对应现有 tuple 位置；
- frozen、slotted，创建后不可修改。

Caller 同时控制 candidate tuple 顺序和选择 index，因此规则是公开配置，不是隐藏在
resolver 代码中的 priority。

**输入与输出**

输入必须是只包含 `DecisionIntent` 的 tuple。输出满足：

```python
resolved is candidates[selected_candidate_index]
```

Resolver 不复制、重建、序列化、相加、平均、裁剪或修改 intents。重复 object reference
仍然可以出现在不同 tuple positions。

**为什么不是 capability 特例**

实现不知道 candidate 来自 TOU、Self Consumption 还是未来 Capability。它不导入具体
Capability，也不检查 capability name、type 或 intent value。

**为什么不能处理物理限制**

Resolution 只决定哪个语义候选继续前进。SOC、battery power、Grid/export limit 和
zero-export 仍由 Constraint 处理；Resolver 不执行 Constraint 或 Evaluation。

**刻意不包含**

- hidden priority、capability name 或 hard-coded first/last；
- weight、score、ranking 或 value-based arbitration；
- intent summation、averaging、clipping 或 normalization；
- TOU/Self Consumption special case；
- optimization、MPC、forecast、schedule 或 AI selection；
- SOC、Battery/Grid limit 或 zero-export；
- Runtime、Dispatch、PCS/BMS 或 device control；
- persistence、telemetry、cache 或 history。

### 4.23 Phase 3 Decision Flow Integration Validation

TASK-051 不增加新的 EMS 算法，而是把已经存在的 Phase 3 组件放入同一条测试链：

```text
TOU / Self Consumption Capability
        |
        v
Capability Composition
        |
        v
Deterministic Intent Resolution
        |
        v
Battery / Grid Constraint Pipeline
        |
        v
Constraint Explanation Chain
        |
        v
Decision Evaluation Cycle
```

**为什么需要集成验证**

单元测试可以证明每个边界独立正确，但不能单独证明对象经过多个边界后仍保持原始身份，
也不能证明 Explanation 或 Cycle 构造没有重复执行 Capability 或 Constraint。
TASK-051 用两个真实能源场景验证完整关系：

- PV surplus：Self Consumption 产生正值充电 candidate，Resolver 显式选择该对象，
  Battery Constraint 限制充电功率，Grid Constraint 接收前一阶段 exact intent；
- PV deficit：Self Consumption 产生负值放电 candidate，Battery Constraint 产生新的
  immutable feasible intent，后续 Grid、Explanation 和 Cycle 保持完整 lineage。

**验证重点**

- `source_intent` 是 Resolver 选中的 exact candidate；
- `feasible_intent` 是 Constraint Pipeline 返回的 exact final wrapper；
- Explanation Entry 按顺序保存每一阶段 exact source/output；
- Explanation Chain 与 Cycle 引用同一个 final feasible artifact；
- 每个 Capability 与 Constraint exactly once；
- Explanation 和 Cycle 只观察已完成对象，不触发重复执行。

测试中的顺序 Composition 与调用探针只用于验证既有抽象合同，不属于生产 Capability、
Resolver、Constraint 或算法实现。

### 4.24 Phase 3 Completion Review

TASK-052 对 TASK-045～051 建立的 EMS Capability Layer 进行冻结审查，结论为 PASS。

冻结后的职责关系是：

```text
Capability：表达业务希望做什么
Composition：按 caller 顺序产生独立 candidates
Resolution：使用显式规则选择一个 source intent
Constraint：决定物理上允许什么
Explanation / Cycle：保存已经完成的身份与证据
Runtime / Device：不属于 Phase 3 决策链
```

**冻结意味着什么**

- `EMSCapabilityBoundary`、Composition、Resolution 和 Intent contracts 已形成稳定入口；
- TOU 与 Self Consumption 可以独立演进，但不能把物理限制带入 Capability；
- Resolver 规则必须显式，不能隐藏 priority、weight、score 或 capability 特例；
- source/feasible/explanation/cycle 的 exact identity 是架构不变量；
- Kernel 不依赖 capability implementation；
- legacy `EMSPolicy`、`DecisionResult`、Runtime 和 Execution 继续隔离。

冻结不代表永远禁止演进，而是任何合同修改都必须通过新的 TASK 与架构审查，不能借具体
Capability 实现顺便改变 Kernel。

### 4.25 EMS Objective Boundary

TASK-053 在 Phase 3 冻结后建立独立 Objective Description Layer：

```text
EMSObjectiveBoundary
        |
        v
ObjectiveCollection
        |
        v
tuple[ObjectiveDescriptor, ...]
```

**Objective 为什么存在**

Objective 只回答“EMS 关注什么”。这个问题与 Capability 的“根据事实产生什么意图”、
Constraint 的“物理上允许什么”以及 Runtime 的“如何执行和推进状态”都不同。
独立边界可以防止业务关注事项被误写成电池动作。

**输入与输出**

- `EMSObjectiveBoundary.describe()` 不读取 `DecisionContext`，也不读取系统状态；
- 输出是 immutable `ObjectiveCollection`；
- 每个 `ObjectiveDescriptor` 只有非空 `name` 和 `description`；
- Collection 保持 caller 提供的 tuple 与 descriptor exact identity。

**为什么不能与 Capability 合并**

Capability 可以产生 `DecisionIntent`，Objective 不可以。Objective 若直接返回充电、
放电或空闲意图，就已经回答了“电池应该做什么”，越过了本层职责。

**刻意不包含**

- concrete objective；
- priority、weight、score 或 ranking；
- optimization 或 resolver；
- intent generation；
- Constraint、Evaluation、Runtime 或 Device 行为。

### 4.26 Objective Activation Boundary

TASK-054 在 Objective Description 之上增加最小 Activation 边界：

```text
ObjectiveCollection
        |
        v
ObjectiveActivationBoundary
        |
        v
ActiveObjectiveCollection
```

**Activation 为什么存在**

完整的 Objective 描述集合与某次使用中处于 active 状态的 Objective 集合不是同一个
概念。Activation 只表达这个集合关系，不解释为什么 active，也不决定谁更重要。

**输入与输出**

- 输入是 exact immutable `ObjectiveCollection`；
- 输出是 frozen/slotted `ActiveObjectiveCollection`；
- 输出保存 exact `source_collection`；
- `active_objectives` 是 caller-produced tuple，其中每个元素必须以 `is` 关系来自 source；
- empty active tuple 合法，caller order 原样保留。

**Exactly once 与只读语义**

一次 `activate()` 调用接收一次 source reference 并返回一个 artifact。边界不会调用
`describe()`，不会重复 activation，也不会运行 Capability、Constraint 或 Evaluation。

**Activation 不是什么**

- 不是 objective priority 或 ranking；
- 不是 objective conflict resolution；
- 不是 weighting、scoring 或 optimization；
- 不是 resolver；
- 不产生 `DecisionIntent`，更不产生设备命令。

### 4.27 Objective-Capability Mapping Boundary

TASK-055 只增加 Objective 与 Capability descriptor 之间的关系表达：

```text
ObjectiveDescriptor
        |
        v
ObjectiveCapabilityMapping
        |
        v
tuple[CapabilityDescriptor, ...]
```

**为什么需要 CapabilityDescriptor**

Objective Layer 需要说明哪些业务能力可以支撑某个关注事项，但不能保存
`TOUEnergyCapability()` 等实现实例。`CapabilityDescriptor` 只有非空 `name` 和
`description`，因此它能表达能力语义，却不能被执行。

**输入与输出**

- Boundary 输入 exact `ObjectiveCollection` 或 `ActiveObjectiveCollection`；
- 输出 immutable `ObjectiveCapabilityMappingCollection`；
- 每个 mapping 保存 exact Objective descriptor；
- `capabilities` 只接受 `tuple[CapabilityDescriptor, ...]`；
- empty mapping 与 empty capability tuple 均合法；
- caller order 和 exact identities 原样保存。

**依赖方向**

```text
objective.mapping -> capability.descriptor
capability -X-> objective
```

Objective 只依赖窄 Capability contract，不依赖 TOU、Self Consumption 或 Resolver
implementation；Capability 也不能反向依赖 Objective。

**Mapping 不是什么**

- 不是 capability selection、ranking 或 priority；
- 不是 scoring、weighting 或 optimization；
- 不执行 Capability；
- 不进行 intent resolution；
- 不生成 `DecisionIntent` 或设备命令。

### 4.28 Capability Discovery Boundary

TASK-056 建立 descriptor-only Capability Discovery 边界：

```text
CapabilityDiscoveryBoundary
        |
        v
AvailableCapabilityCollection
        |
        v
tuple[CapabilityDescriptor, ...]
```

**为什么需要 Discovery Boundary**

Objective-Capability Mapping 描述“某个 Objective 可以由哪些能力支撑”，但它不说明
未来 provider 当前报告了哪些 capability descriptors。Discovery 将“可用描述观察”独立
出来，同时避免把设备扫描、协议访问或 Capability 构造带入描述层。

**不可变输出与 identity**

- `AvailableCapabilityCollection` 是 frozen/slotted；
- 唯一字段是 `tuple[CapabilityDescriptor, ...]`；
- exact tuple、caller/provider order 与每个 descriptor identity 原样保存；
- empty availability 合法；
- 不 copy、rebuild、sort、deduplicate 或 normalize。

**Discovery 不是什么**

- 不连接设备，不读取 CAN、Modbus、PCS 或 BMS；
- 不创建、保存或执行 Capability instance；
- 不进行 Objective-Capability matching；
- 不进行 selection、ranking、priority、scoring 或 optimization；
- 不执行 activation；
- 不生成或解析 `DecisionIntent`。

Discovery 只回答“有哪些 capability descriptors 被报告为 available”，不回答“应该选择
哪个能力”或“电池应该做什么”。

### 4.29 Capability Matching Boundary

TASK-057 在 Required 与 Available descriptor collections 之间建立关系事实边界：

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

**为什么 Matching 与 Selection 分离**

Matching 只陈述“这个 exact required descriptor 与这个 exact available descriptor 存在
关系”。Selection 则要回答“最终使用哪个能力”。如果 Matching 模型包含 score、priority、
selected flag 或 fallback，它就已经越过关系证据边界，开始承担仲裁职责。

**不可变关系与 identity**

- Required 与 Available collections 都只保存 descriptor tuples；
- `CapabilityMatch` 保存 exact required/available descriptor references；
- `CapabilityMatchCollection` 保存 exact source collections、exact match tuple 与
  exact `missing_required` tuple；
- 每个 match 必须以 `is` 关系来自对应 source collection；
- 每个 missing descriptor 必须以 `is` 关系来自 required source collection；
- 每个 required descriptor 必须且只能属于 matched 或 `missing_required`，不允许遗漏或重叠；
- equal-but-reconstructed descriptor 被拒绝；
- empty required、available、matches 与 missing tuples 在满足完备性契约时合法。

**Matching 不是什么**

- 不根据 name 自动比较；
- 不 ranking、scoring、priority、weighting 或 selection；
- 不 optimization、conflict resolution 或 fallback；
- 不 activation 或执行 Capability；
- 不连接设备，不读取 CAN/Modbus；
- 不生成或解析 `DecisionIntent`。

### 4.30 Capability Activation Boundary

TASK-058 在已完成的 matching facts 之上建立 descriptor-only activation 状态边界：

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

**为什么 Activation 与 Matching 分离**

Matching 回答“required descriptor 与 available descriptor 是否存在关系”；Activation 回答
“已匹配的 available descriptor 当前被表达为 active 还是 inactive”。如果把 active 状态写入
`CapabilityMatch`，关系事实就会被后续生命周期状态污染。

**不可变状态与 identity**

- `ActiveCapabilityCollection` 是 frozen/slotted；
- source 是 exact `CapabilityMatchCollection` reference；
- active 与 inactive 都是 caller-supplied descriptor tuples；
- tuple、顺序和 descriptor identity 原样保持；
- 每个 descriptor 必须以 `is` 来自 source matches 的 available descriptor；
- 每个 matched descriptor 必须且只能属于 active 或 inactive，不能遗漏或重叠；
- 不 copy、rebuild、sort、deduplicate 或 normalize。

**Activation 不是什么**

- 不实现 priority、ranking、scoring、weighting 或 selection；
- 不实现 optimization、conflict resolution 或 fallback；
- 不创建或执行 Capability instance；
- 不生成或解析 `DecisionIntent`；
- 不调用 Constraint、Runtime、Execution 或 Device；
- 不连接 CAN、Modbus、PCS 或 BMS。

### 4.31 Objective-Capability Activation Composition

TASK-059 将一个 exact Objective descriptor 与一个已经完成的
`ActiveCapabilityCollection` 组合成 immutable relationship artifact：

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

**为什么直接保存完整 ActiveCapabilityCollection**

Composition 的职责是表达关系，不是从 active capabilities 中再次挑选。如果再接受一个
capability subset，composition 就会隐式承担 selection，并可能遗漏已经 active 的 descriptor。
因此结果直接保存 exact `ActiveCapabilityCollection` reference，完整性由对象结构保证。

**Identity 与重复保护**

- `composition.objective is original_objective`；
- `composition.active_capabilities is original_active_collection`；
- nested active tuple、顺序和 descriptor identities 原样保持；
- 同一个 descriptor identity 不能在 active tuple 中重复；
- reconstructed descriptor 无法通过 `ActiveCapabilityCollection` 的 source identity 验证；
- empty active collection 仍是完整且合法的 composition。

**Composition 不是什么**

- 不 selection、ranking、priority、scoring 或 weighting；
- 不 optimization、conflict resolution 或 fallback；
- 不执行 Capability activation 或 Capability implementation；
- 不生成 `DecisionIntent`；
- 不调用 Constraint、Evaluation、Runtime、Execution 或 Device。

## 5. Phase 4：Objective & Capability Architecture

Phase 4 解决的不是“电池现在充电还是放电”，而是更靠前的两个问题：

1. EMS 当前关心什么目标？
2. 系统拥有哪些可描述、可匹配、可激活并能与目标建立关系的能力？

如果不先回答这两个问题，策略通常会把业务目标、设备能力、算法选择和执行状态塞进同一个
对象。短期看调用简单，长期却很难解释某个决策到底来自目标、能力、约束还是设备状态。

Phase 4 用一组不可变边界把这段语义拆开：

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

这里的箭头表示语义演进顺序，不表示 Phase 4 已经建立自动运行流水线。所有边界都停留在
descriptor、relationship 和 status 层。

### 5.1 为什么 EMS 需要 Objective 层

EMS 会面对多种业务关注点，例如降低购电成本、提高光伏自用率、限制需量或保持备用容量。
这些关注点首先是“系统为什么要决策”，并不是“电池应该输出多少 kW”。

`ObjectiveDescriptor` 只保存目标名称和描述，使目标可以被：

- 明确命名，而不是隐藏在策略类名中；
- 作为 immutable evidence 被其他边界引用；
- 与 Capability descriptor 建立关系；
- 在不触碰 Kernel、Runtime 或 Device 的情况下演进。

如果没有 Objective 层，业务目标往往只能从策略分支、配置键或设备命令反推。这样既不利于
审查，也不利于未来解释“为什么这次决策使用了某种能力”。

### 5.2 Objective 与 Strategy 的区别

| 概念 | 回答的问题 | 典型输入 | 典型输出 | 不负责 |
| --- | --- | --- | --- | --- |
| Objective | EMS 关心什么 | 描述事实 | `ObjectiveDescriptor` | 计算电池动作 |
| Strategy/Policy | 根据事实希望系统做什么 | `DecisionContext` | `DecisionIntent` | 设备执行与物理约束 |

“降低成本”是 Objective；“低价时产生充电意图”是 Strategy。把两者合并会让目标描述携带算法，
也会让算法成为目标的唯一实现。EOS 将二者分离，使同一个 Objective 将来可以由不同
Capability 支撑，而同一个 Capability 也可以服务多个 Objective。

### 5.3 为什么 Capability 要独立建模

Capability 表达“系统具备哪一种业务能力”，而不是某个 Python 对象正在运行。独立建模有
三个工程收益：

- Objective 可以依赖稳定的 Capability contract，而不是具体实现；
- Discovery、Matching、Activation 可以分别留下证据；
- Capability implementation 可以变化，而 Objective 和 Kernel contract 不必变化。

Phase 4 不创建或执行 Capability instance。它只处理 `CapabilityDescriptor`，从而避免把设备
连接、运行时生命周期或策略状态带入 Objective 架构。

### 5.4 CapabilityDescriptor 的作用

`CapabilityDescriptor` 是能力的稳定描述身份，字段只有非空 `name` 与 `description`。它不是：

- Capability implementation；
- 可调用函数或 factory；
- Device/PCS/BMS 句柄；
- 优先级、评分或选择结果；
- `DecisionIntent`。

Descriptor 的价值在于让边界之间传递同一个对象引用。Mapping、Discovery、Matching、
Activation 和 Composition 都能通过 `is` 判断自己观察的是不是同一个能力描述，而不是一个
值相等但来源不明的重建对象。

### 5.5 Discovery、Matching 与 Activation 的区别

| 阶段 | 核心问题 | 输入 | 输出 | 非职责 |
| --- | --- | --- | --- | --- |
| Discovery | 当前报告有哪些能力描述可用？ | 无调用参数 | `AvailableCapabilityCollection` | 匹配和选择 |
| Matching | required 与 available 之间有哪些关系，哪些 required 缺失？ | required + available | `CapabilityMatchCollection` | 排名和激活 |
| Activation | 已匹配能力处于 active 还是 inactive？ | matching result | `ActiveCapabilityCollection` | 激活算法和执行 |

三者不能合并，因为它们表达不同时间点和不同证据：

- Discovery 只观察 availability；
- Matching 只表达 required-to-available relationship；
- Activation 只表达 matched descriptor status。

把三者合并会让“没有发现”“没有匹配”“没有激活”变成同一种空值，系统将失去可解释性。

`CapabilityDiscoveryBoundary.discover()` 没有调用参数；该 boundary 本身定义 provider contract，
并返回 `AvailableCapabilityCollection`。调用方负责提供具体 provider implementation，但 Phase 4
没有建立 Mapping、Required Capability、Discovery 与 Matching 之间的自动连接。

### 5.6 Available ≠ Matched ≠ Active

一个 Capability 可以 available，但没有任何当前 Objective 要求它，因此未 matched；也可以
已经 matched，但当前状态为 inactive。反过来说，active descriptor 必须来自已匹配结果，不能
凭空重建。

```text
Available
   |  只说明被报告可用
   v
Matched
   |  说明满足了某个 required descriptor relationship
   v
Active
      说明已匹配 descriptor 的当前激活状态
```

这三个集合不是同义词，也不能用一个布尔字段替代。分别建模后，审查者可以准确判断缺口发生
在哪一层。

### 5.7 Identity Preservation 为什么重要

EOS 使用 immutable object identity 建立证据链。以 Capability 为例：

```python
match.available is available_collection.capabilities[index]
active_capability is match.available
composition.active_capabilities is original_active_collection
```

如果边界复制或序列化后重建 descriptor，即使字段值相等，也无法证明它来自原始 Discovery 或
Matching 结果。Identity preservation 因此不是性能优化，而是 lineage contract：它让后续层
可以证明自己引用的是哪个已完成事实。

### 5.8 Immutable Contract 为什么重要

Phase 4 的 collection 全部使用 tuple，数据模型使用 frozen/slotted dataclass。这样做保证：

- Mapping 关系不会在 Matching 后被悄悄修改；
- Matching 结果不会在 Activation 后改变；
- Activation 状态不会在 Composition 中被追加或删除；
- 同一个对象引用在审查、测试和未来 replay 中具有稳定含义；
- 边界无需拥有 cache、history 或 runtime state。

`frozen=True` 本身并不足够；如果字段中放入 list 或 dict，内部仍可变化。因此 EOS 同时要求
tuple-only collection，并显式拒绝 mutable container。

### 5.9 TASK-057 missing_required 契约修复案例

TASK-057 的第一版 `CapabilityMatchCollection` 只有 `matches`。测试可以验证已有 match 的类型、
identity 和 immutability，但无法表达 required capability 没有匹配结果。

这会产生一个架构歧义：某个 required descriptor 不在 `matches` 中，究竟表示“明确缺失”，还是
“调用方忘记处理”？两种状态在数据上完全相同。

正式审查因此判定 BLOCK MERGE。修复增加：

```python
missing_required: tuple[CapabilityDescriptor, ...]
```

并建立 complete coverage contract：每个 required descriptor 必须且只能属于 `matches` 或
`missing_required`。遗漏和跨类别重叠都会被拒绝，所有引用继续保持 exact identity。

这个案例说明：

> 测试通过只能证明已写出的行为符合测试，不能证明架构契约已经覆盖所有必要状态。

架构审查必须继续追问“哪些业务事实目前无法表达”。只有可表达状态完整，immutable model 才能
成为可靠边界。

### 5.10 Phase 4 的边界

Phase 4 已完成 Objective description、Objective activation、Objective-Capability mapping、
Capability discovery、matching、activation 和 composition，但明确没有实现：

- `DecisionIntent` generation；
- optimization、ranking 或 conflict resolution；
- Runtime orchestration；
- Device、CAN、Modbus、PCS 或 BMS integration。

因此 Phase 4 的最终产物是“可审查的 Objective 与 Capability 证据结构”，不是完整 EMS
执行链。

## 6. Phase 5：Decision Formation

Phase 5 从 TASK-061 开始建立决策形成语义。它不会把 Phase 4 Objective/Capability evidence
直接变成设备动作，而是先冻结“意图是什么”的最小语言。

### 6.1 TASK-061 DecisionIntent Contract

Phase 5 的 `decision_formation.DecisionIntent` 只有一个 immutable 字段：

```text
action = charge | discharge | idle
```

- `charge`：语义上希望充电；
- `discharge`：语义上希望放电；
- `idle`：语义上不希望充电或放电。

这些 action 不定义功率大小，也不通过正负功率表达设备方向。不同 PCS、BMS 或协议可能采用
不同 sign convention，Decision Formation 不能把这些设备语义固化进 Intent。

### 6.2 DecisionIntent 不等于 Command

```text
DecisionIntent
    表达希望做什么

Command
    表达未来提交什么操作
```

TASK-061 不生成 Command，不包含 device address、CAN/Modbus frame、执行状态或 Runtime 所有权。
未来从可行 Intent 到 Command 的转换必须由新的独立边界定义。

### 6.3 为什么建立独立合同

Phase 3 已有 `kernel.decision.DecisionIntent`，它保存
`battery_power_intent_kw`，并被 Capability、Constraint 和 Evaluation 使用。直接把该字段改为
action 会破坏已审查的路径。

因此 TASK-061 新增独立合同：

```text
Phase 3: kernel.decision.DecisionIntent(battery_power_intent_kw)
Phase 5: decision_formation.DecisionIntent(action)
```

两者没有 inheritance、adapter、alias 或自动转换。TASK-061 只建立 artifact，不生成实际决策，
也不访问 Objective、Capability implementation、Constraint、Optimization、Runtime 或 Device。

### 6.4 后续边界

Phase 5 计划按独立 TASK 继续审查：

```text
TASK-061 Intent Contract
        |
        v
TASK-062 Formation Boundary
        |
        v
TASK-063 Resolution
        |
        v
TASK-064 Constraint Evaluation
```

当前只有 TASK-061 artifact 已进入实现阶段，后续能力不能从文档描述推断为已经存在。

## 7. Phase 6：Simulation Core

Phase 6 位于未来 Phase 5 feasible decision artifact 之后，但 Simulation 不等于 Runtime，也不等于
Device Execution。Simulation 只接收显式输入并计算模拟响应；它不拥有 loop、scheduler、真实设备、
Command 或通信协议。

### 7.1 TASK-065 SimulationStepIdentity

TASK-065 只建立最小 identity/time artifact：

```text
SimulationStepIdentity
├── sequence: non-negative, zero-based integer
├── duration_seconds: positive finite raw seconds
└── timestamp: timezone-aware datetime | explicit None
```

三个事实全部由 caller 显式提供。构造过程不会读取“现在”、生成 UUID、推进下一 step 或调用任何
component model。

当 timestamp 存在时，EOS 保留 exact reference：

```text
step.timestamp is original_timestamp
```

这意味着 validation 可以确认 timezone，但不能复制 datetime、转换 timezone 或替换调用方证据。

### 7.2 为什么先定义时间合同

PV、Load、Tariff、Battery 和 Grid 模型都需要共享明确的 step duration 或绝对时间语义。如果各模型
自行读取 clock，就无法保证相同输入得到可重复观察。TASK-065 因此先冻结共同语言，但不提前创建
任何 component、aggregate State、Scenario、Step Input 或 Step Result。

后续顺序保持：component contracts 在 TASK-066～071 定义，aggregate contracts 只在 TASK-072
建立。

### 7.3 TASK-066 PV Model Contract

TASK-066 把“PV 模拟输入是什么”和“某个模型如何计算”分开。Input 只保存 exact step identity 与
caller 显式提供的 `available_power_kw`；Result 保存 exact Input 与 `actual_power_kw`。

```text
PVSimulationInput(step, available_power_kw)
        |
        v
abstract PVSimulationModelBoundary
        |
        v
PVSimulationResult(actual_power_kw)
```

两个功率字段都使用非负 finite raw kW。`actual_power_kw` 不能超过 availability，但 contract 不计算
actual 值。它不读取 irradiance、天气、MPPT、逆变器或设备遥测。

Identity 关系：

```text
input.step_identity is original_step
result.simulation_input is original_input
```

这让未来不同 PV physics implementation 可以替换，同时 aggregate Simulator 仍能证明每个输出来自
哪一个 exact step 输入。

### 7.4 TASK-067 Load Model Contract

Load boundary 使用 caller 显式提供的 `demand_power_kw`，而不是在 contract 内预测负载或模拟用户
行为。Result 的 `actual_power_kw` 表示该 step 的模拟消费 observation。

```text
LoadSimulationInput(step, demand_power_kw)
        |
        v
abstract LoadSimulationModelBoundary
        |
        v
LoadSimulationResult(actual_power_kw)
```

Demand 与 actual 都是非负 finite raw kW，actual 不得超过 explicit demand。这个上界是 artifact
完整性规则，不是 load shedding、Demand Response 或用户行为算法。

Identity 保持：

```text
input.step_identity is original_step
result.simulation_input is original_input
```

因此未来预测、profile generation 或行为模型若需要加入，必须作为独立实现或输入来源，不得改变
基础 Load boundary。

### 7.5 TASK-068 Tariff Model Contract

Tariff boundary 把“当前模拟 step 的价格事实”与“TOU 策略应该做什么”分开。Input 必须引用带有
timezone-aware timestamp 的 exact step，并显式携带 import/export prices。

```text
TariffSimulationInput(step, import_price, export_price)
        |
        v
abstract TariffSimulationModelBoundary
        |
        v
TariffSimulationResult(import_price, export_price)
```

价格单位固定为 signed finite raw CNY/kWh。允许负电价，不进行 currency conversion、hidden scaling、
TOU window selection 或 forecasting。

```text
input.step_identity is original_step
result.simulation_input is original_input
```

Tariff Model 只产生模拟价格 observation，不能根据高低电价生成 charge/discharge Intent。

### 7.6 TASK-069 Battery Simulation Actuation Contract

Battery actuation 是“已经允许的决策”与“未来 Battery 模型接收的功率请求”之间的证据边界：

```text
FeasibleDecisionIntent
        |
        v
BatterySimulationActuation
        |
        v
Future Battery Simulation Model
```

它保存 exact `source_feasible_decision`，因此可以验证：

```text
actuation.source_feasible_decision is original_feasible_decision
```

`battery_power_kw` 使用 signed finite raw kW：正值表示充电，负值表示放电，零表示空闲。这个符号约定
属于 Simulation actuation contract，不是设备协议，也不代表已经生成 Command。

Actuation 不根据 source decision 计算功率，不裁剪功率，不执行 SOC/SOH、效率、退化或温度模型，也不
推进 Battery state。caller 必须显式提供功率；后续 TASK-070 才定义 Battery model contract。

为什么不把 actuation 合并进 Decision 或 Command：

- Decision 表达经过约束后的允许结果；
- Simulation Actuation 表达模型将要观察的显式物理输入及其 provenance；
- Command 属于真实设备执行语义；
- 合并会让模拟、决策与设备执行失去独立替换和回放能力。

### 7.7 TASK-070 Battery Simulation Model Contract

TASK-070 在 actuation 之后加入最小 Battery state-transition seam：

```text
step + source state + actuation
        |
        v
BatterySimulationInput
        |
        v
abstract BatterySimulationModelBoundary
        |
        v
BatterySimulationResult(next state, actual power)
```

`BatterySimulationState.soc` 是 `[0, 1]` 的 raw unitless fraction。Input 保存 exact step、source state 与
actuation；Result 保存 exact Input 和 caller/model 提供的 immutable next state。没有变化时 next state
可以与 source state 是同一对象，发生变化时则可以是新的 immutable state。

Result 的 `actual_power_kw` 延续正值充电、负值放电、零值空闲的 signed raw kW 约定，但 contract 不
计算 SOC、不计算效率，也不要求 actual power 必须等于 actuation power。后者属于未来 concrete model，
不能隐藏在 artifact validation 中。

这个设计把四件事分开：

- feasible decision：允许做什么；
- actuation：模型收到什么显式功率请求；
- model：如何计算模拟响应；
- immutable next state：本 step 完成后的观察。

### 7.8 TASK-071 Grid Simulation Model Contract

Grid component contract 只描述一个 step 的 requested exchange 与 actual exchange：

```text
step + requested_grid_power_kw
        |
        v
GridSimulationInput
        |
        v
abstract GridSimulationModelBoundary
        |
        v
GridSimulationResult(actual_grid_power_kw)
```

两种功率都使用 signed finite raw kW：正值表示从 Grid import，负值表示向 Grid export，零表示平衡。
Input 保存 exact step，Result 保存 exact Input。

为什么 requested 与 actual 分开：requested 是 caller 明确提供给模拟模型的事实；actual 是模型输出的
观察。Contract 不要求二者相等，也不负责解释差值。这样未来具体模型可以独立演进，但 artifact 本身
不会偷偷加入 Grid limit、Zero Export 或 power-balance 算法。

Grid model 不读取 PV、Load 或 Battery output 来自动计算 Grid power。多个 component 如何形成系统功率
平衡属于后续 aggregate contract，而不是单一 Grid component 的职责。

### 7.9 TASK-072 Aggregate Simulation Contract

TASK-072 把已经独立 review 的 component artifacts 组合成一致证据，但不执行任何 model：

```text
exact component inputs -> SimulationStepInput
exact component results -> SimulationState
input + state          -> SimulationStepResult
ordered step inputs    -> SimulationScenario
```

`SimulationStepInput` 要求 PV、Load、Tariff、Battery、Grid inputs 都引用同一个 exact
`SimulationStepIdentity`。`SimulationState` 保存同一步的 exact component results。
`SimulationStepResult` 进一步验证每个 result 的 `simulation_input` 就是 aggregate input 中对应的 exact
对象，而不是 value 相等的重建版本。

```text
state.battery_result.simulation_input is step_input.battery_input
```

这种 identity 验证让 provenance 可以追溯到 Battery actuation，再追溯到 exact feasible decision。

`SimulationScenario.steps` 只能是 tuple，并保留 caller 顺序与 tuple identity。Scenario 不排序、不去重、
不生成时间、不执行 steps，也不拥有 Runtime history。它描述“准备模拟哪些输入”，不是“负责跑模拟”。

为什么 State 仍不是 Runtime state：这里的 `SimulationState` 是一个完成 step 的 immutable aggregate
observation。它没有 update/advance 方法、cache、current pointer 或 loop；下一步输入必须由未来明确边界
提供，不能在 artifact 内偷偷推进。

### 7.10 TASK-073 Phase 6 Integration Validation

TASK-073 不增加生产模型，而是用 test-only recording models 把 TASK-065～072 的 contracts 串成完整证据
链。PV、Load、Tariff、Battery、Grid models 各接收对应 exact input，并且各执行一次；随后已有 aggregate
artifacts 只保存这些结果，不重复执行。

```text
exact step
  -> exact component inputs
  -> test-only model calls (once each)
  -> exact component results
  -> SimulationState
  -> SimulationStepResult
```

测试同时追踪 Battery provenance：

```text
feasible decision
  -> BatterySimulationActuation
  -> BatterySimulationInput
  -> BatterySimulationResult
  -> SimulationState
  -> SimulationStepResult
```

充电/import 场景验证正功率语义，放电/export 场景验证负功率语义；这些测试不计算 power balance，也不
宣称两组数值之间存在自动关系。Scenario 测试还故意使用非时间顺序的 caller tuple，以证明 contract
保持输入顺序而不会偷偷排序或执行。

“integration validation”与“production orchestration”不同：前者证明已有合同可以正确组合，后者会拥有
调用流程和失败边界。TASK-073 只做前者。

### 7.11 TASK-074 Phase 6 Completion Review

TASK-074 把 Phase 6 冻结为“模拟合同平台”，而不是“可运行的仿真器”。完成审查后，EOS 已经具备：

- 显式且不拥有 clock 的 step identity/time contract；
- PV、Load、Tariff、Battery、Grid 的 immutable input/result 与 abstract model boundaries；
- feasible decision 到 Battery simulation actuation 的 exact provenance；
- 保存 exact component evidence 的 step/state/result/scenario contracts；
- exactly-once test evidence，证明 aggregate construction 不会重复执行 model。

学习时最重要的分界是：

```text
Feasible Decision
        -> Simulation Actuation
        -> Model Observation
        -> Immutable Simulation Evidence

以上均不等于：
Runtime Loop / Device Command / Physical Side Effect
```

Phase 6 仍没有 production physics、power balance、SOC transition、scenario runner 或 step progression。
“合同完整”表示未来实现有稳定插槽与可验证 provenance，不表示这些未来能力已经存在。

## 7.12 TASK-075 Simulation Model Binding Contract

Phase 6 定义了“模型必须遵守什么接口”，但没有回答“本次执行具体使用 caller 提供的哪个模型对象”。TASK-075
建立这个最小关系：

```text
component model boundary + exact caller model
        |
        v
SimulationModelBinding
        |
        v
SimulationModelBindingCollection
```

Binding 只表达 ownership/reference relationship。它不执行、选择、创建或管理模型。

为什么同时保存 contract 和 model：contract 明确模型承担 PV、Load、Tariff、Battery 或 Grid 中哪一种职责；
model 则是 caller 已经创建并拥有的 exact instance。系统不用字符串名称、registry、factory 或 reflection 猜测关系。

为什么 binding 使用 identity-based equality：如果重新创建一个字段相同的 binding，它只是“描述相同”，不是原始
caller artifact。因此 collection membership 不能把 reconstructed binding 当成原 binding。

Collection 保存 exact tuple 和 caller order，不排序、不去重、不补全。即使 caller 重复放入同一个 binding，TASK-075
也只保存这个事实，不推断它应执行几次；execution semantics 属于后续独立边界。

### 7.13 TASK-076 Single-Step Simulation Executor Boundary

TASK-076 首次让 Phase 6 contracts 发生一次真实但严格受限的 model invocation：

```text
one exact SimulationStepInput
        +
caller-owned bindings
        |
        v
SingleStepSimulationExecutor
        |
        v
SimulationState -> SimulationStepResult
```

为什么先检查 completeness 再调用：TASK-075 collection 可以表达 partial 或 duplicate facts，但一次完整 step 必须拥有
PV、Load、Tariff、Battery、Grid 各一个 model。如果边执行边发现缺失，前面的 model 已经被调用，就会产生半完成执行。
因此 TASK-076 在任何调用之前验证“五类各且仅一个”。

为什么按 caller order：BindingCollection 已保存显式顺序。Executor 尊重这个输入，不排序、不推断依赖、不隐藏优先级。
成功时每个 model 恰好执行一次；失败时立即停止，并把同一个异常交还 caller。

Executor 仍不是 Runtime：它只处理一个显式 step，没有 loop、clock、current pointer、retry、history 或下一 step 生成。
它也不是 Device Execution：这里调用的是 simulation model boundary，不是 PCS/BMS 或 Command adapter。

### 7.14 TASK-077 Simulation Execution Trace / Evidence Contract

执行完成后，系统需要保存“哪些现有对象共同构成这次结果”，但保存证据不能再次执行。TASK-077 引入：

```text
bindings + completed step result
        |
        v
SimulationExecutionTrace
        |- exact input
        |- exact state
        |- exact result
        |- exact binding collection
```

`create()` 只读取 `step_result.simulation_input` 和 `step_result.state` 的现有引用。它不调用 executor，不调用
model，也不重新创建 component results。

为什么称为“structurally completed evidence”：Trace 能证明 result 引用 exact input 和 exact state；既有 aggregate
contracts 又能证明 state 中每个 component result 引用 exact component input。但当前 component result 不保存
model identity，所以 Trace 不能独立证明某个 model 一定执行过。它只保留 caller 关联的 exact binding collection，
不把关联夸大为不可伪造的执行证明。

这体现 EOS 的证据原则：只陈述对象结构能够证明的事实，不通过命名暗示更强保证。

### 7.15 TASK-078 Scenario Execution Boundary

TASK-076 只能执行一个明确 step，TASK-077 只能观察一个已完成 step。TASK-078 把两者组合到 caller 已经完整提供的
`SimulationScenario` 上：

```text
explicit caller-ordered scenario steps
        +
exact caller-owned bindings
        |
        v
ScenarioExecutionBoundary
        |
        v
one exact SimulationExecutionTrace per completed step
        |
        v
ScenarioExecutionResult
```

“Scenario execution”不等于“Scenario progression”。Boundary 只遍历现有 `scenario.steps`，不根据前一步结果生成
下一步，也不把 Battery next state 自动写入下一项输入。每个 step 的 source state、actuation 和 component inputs
仍由 caller 明确给出。

为什么必须复用 single-step executor：PV、Load、Tariff、Battery、Grid binding completeness、caller binding order、
result type 和 failure semantics 已由 TASK-076 定义。如果 scenario 层重新实现，会形成两套可能分歧的执行规则。

为什么结果保存 trace 而不是只保存数值：每个 trace 继续保留 exact step input、state、step result 和 bindings。
`ScenarioExecutionResult` 又验证 trace 与 `scenario.steps` 在同一 index 上使用 exact identity，因此 missing、extra、
reordered 或 differently-bound evidence 都不能冒充完整场景结果。

失败采用 stop-first：同一个异常原样传播，不返回半完成 result。此前已经被调用的 caller-owned test/model object
可能已经观察到调用；本边界不提供 rollback、retry 或 checkpoint。空 scenario 则直接产生空 trace tuple，且不调用
任何 model。

### 7.16 TASK-079 Explicit Step Progression Contract

Scenario order 只回答“以什么顺序执行 caller 已经给出的 steps”，并不回答“下一步输入从哪里来”。TASK-079 把后者
建模为一个显式 provenance relation：

```text
completed previous trace/result
        +
caller-created next input
        |
        v
SimulationStepProgression
```

为什么不能让 Simulation 自动生成下一步：一旦 simulation 根据当前结果创建 timestamp、sequence、load、PV、tariff
或 actuation，它就开始拥有未来事实、时间推进和生命周期，实际上变成了 Runtime。TASK-079 因此只验证 caller
已经提供的对象关系。

Battery 是当前 component contracts 中唯一显式暴露 source state 与 next state 的模型。其 lineage 为：

```text
previous battery source_state
        |
        v
previous BatterySimulationResult.next_state
        |
        | exact identity
        v
next BatterySimulationInput.source_state
```

这里没有 SOC 计算或状态复制。若 caller 新建一个数值相同的 `BatterySimulationState`，identity 已经不同，不能冒充
model 实际产生的 next state。同理，progression 保存的 previous result 必须就是 previous trace 中的 exact result，
value-equal reconstruction 会被拒绝。

下一步的 timestamp 和 duration 已经包含在 caller-supplied `SimulationStepIdentity` 中。Progression 不读取 clock、
不增加时间、不验证时间先后，也不执行下一步。因此必须持续区分：

```text
Scenario ordering != Step generation
Step progression != Time scheduling
Simulation != Runtime
```

### 7.17 TASK-080 Phase 7 Integration Validation

单元测试证明每个 contract 自身成立，integration validation 则回答“这些 contract 组合后是否仍保持原来的边界”。
TASK-080 使用 test-only component models 验证完整链路：

```text
Bindings + Scenario
        |
        v
Scenario Execution
        |
        v
Single-Step Execution
        |
        v
Trace Evidence
        |
        v
Explicit Progression Relation
```

成功路径证明 caller step order 与 binding order 没有被改写，每个成功 step 的每个 model 恰好调用一次，并且 scenario、
bindings、steps、traces、results 和 progression 全部保持 direct identity。两组独立但等价的 test models 对同一组明确
输入产生相同观察值，同时各自 evidence 仍是独立对象。

失败路径故意让第二个 step 的 component 抛出一个预先创建的异常对象。验证结果是：同一个异常原样传播；当前 step
后续 bindings 和未来 steps 不执行；失败 component 不 retry；调用方收不到伪造的成功 `ScenarioExecutionResult`。

为什么 TASK-080 不新增 production integration service：TASK-078 已经是 production composition boundary。为了测试再
增加一层只会复制职责。测试使用的 recording models 只存在于 tests，不是 EOS 提供的 production physics。

完整冻结报告见 `docs/phase-summary/EOS_Phase7_Deterministic_Simulation_Execution_v1.0.md`。

### 7.18 TASK-081 Phase 7 Completion Review

TASK-081 不增加代码，而是把 Phase 7 已经由实现和测试证明的边界正式冻结下来。完成性审查回答的不是“还能增加什么”，
而是“当前系统已经保证什么，以及明确不保证什么”。

冻结后的学习重点是三组区别：

```text
deterministic execution != Runtime lifecycle
scenario ordering != future step generation
structural trace != independent proof of model invocation
```

确定性来自 caller 提供的 immutable facts、明确顺序和 deterministic models，不来自 global cache 或隐藏状态。每个 contract
只对自己直接保存的对象承担 identity guarantee：scenario result 保存 exact scenario/bindings，trace 保存 exact
input/state/result/bindings，progression 保存 exact previous evidence 与 caller next input。不要把这些局部且明确的关系扩张为
未实现的自动跨层 lineage。

Progression 尤其不能被理解成“模拟器算出下一步”。下一步的 timestamp、duration、component inputs 与 Battery source state
都由 caller 提供；合同只验证其中明确要求的 provenance。这样 Simulation 始终不会偷偷变成 Scheduler 或 Runtime。

TASK-081 也确认 Phase 7 没有 Command、Dispatcher、PCS/BMS、CAN/Modbus/MQTT、EMS strategy、Optimization、Forecast、
persistence 或 history ownership。未来若引入这些能力，必须建立新的显式边界，不能修改 Phase 7 的含义。

### 7.19 TASK-082：从冻结架构走向 24 小时 Demo 输入

TASK-082 是应用层开发的第一步。它不再增加通用抽象边界，而是回答一个具体问题：运行 24 小时储能仿真前，调用方必须明确
提供哪些事实？答案是 24 个小时的 PV、Load、Tariff 曲线，电池参数、初始 SOC，以及每小时明确的 step identity。

```text
24-hour caller facts
        |
        v
DailySimulationScenarioInput
        |
        v
future demo runner
        |
        v
frozen Phase 6/7 simulation contracts
```

这里最重要的区别是 `DailySimulationScenarioInput != SimulationScenario`。前者是用户可准备的数据集；后者是 Phase 6 中已经
拥有完整 component inputs 的可执行场景。Battery actuation、下一 SOC 和 Grid power 不能在读入曲线时提前猜测，否则输入层
就会偷偷承担策略和物理计算。

所有曲线都使用长度为 24 的 tuple。PV/Load 单位是 kW，Tariff 单位是 CNY/kWh；SOC 和效率使用未缩放的 `[0, 1]`
fraction。时间由调用方通过 24 个连续、timezone-aware、每步 3600 秒的 `SimulationStepIdentity` 提供。合同只验证这些事实，
不排序、不补值、不读取 clock，也不构造未来执行步骤。

`BatteryParameters` 同样只描述事实：容量、充放电功率限制、效率和 reserve SOC。TASK-082 不执行限制、不更新 SOC，也不
生成 Battery power。这样后续 concrete model 和 runner 可以复用这些事实，同时 Phase 5～7 contract 保持冻结。

### 7.20 TASK-083：第一个 Concrete PV Profile Model

TASK-083 开始把输入事实接到可执行 component model，但仍保持非常窄的职责：`PVProfileSimulationModel` 只把一个小时的
`PVSimulationInput.available_power_kw` 变成同值的 `PVSimulationResult.actual_power_kw`。

```text
24h PV curve 中的一个值
        |
        v
exact PVSimulationInput
        |
        v
PVProfileSimulationModel
        |
        v
PVSimulationResult
```

为什么 model 不在构造函数中再保存整条 24h curve？因为 TASK-082 的 daily input 已经是 profile 的 caller-owned source。
未来 runner 会为每个小时显式构造 `PVSimulationInput`。如果 model 再保存一份 curve，就会出现两个事实来源，还会把 sequence
lookup 和 scenario-length 假设带进 component model。

这个最小模型也展示了 deterministic 与 object identity 的区别。同一 input 重复执行会得到相同的 power value，但每次产生
独立 immutable result；每个 result 都通过 `result.simulation_input is original_input` 保存来源。确定性不要求缓存或返回同一个
result 对象。

当前 `actual_power_kw == available_power_kw` 只是 profile demo 的明确语义，不是天气、辐照度、温度、MPPT、逆变器或预测模型。
这些能力若未来需要，必须以新的 concrete implementation 引入，不能修改已经冻结的 Phase 6 contract。

### 7.21 TASK-084：Concrete Load Profile Model

`LoadProfileSimulationModel` 延续 PV model 的最小模式：未来 runner 从 TASK-082 的 24h Load curve 取出一个明确值，放入
`LoadSimulationInput.demand_power_kw`；model 只返回引用 exact input 的 `LoadSimulationResult`。

```text
24h Load curve 中的一个值
        |
        v
exact LoadSimulationInput
        |
        v
LoadProfileSimulationModel
        |
        v
LoadSimulationResult
```

这里的 `actual_power_kw == demand_power_kw` 表示 profile replay，不是用户行为仿真。model 不知道家电类型，不生成随机负载，
不做 forecast 或 AI prediction，也不根据电价改变 demand。它只把 caller fact 转换为 Phase 6 result。

同一输入重复执行时，输出数值相同，但 result artifact 各自独立；每个 result 都保持 exact input 和 exact step identity。
model 使用 empty slots，不保存 curve、cache 或 history。这样 deterministic execution 来自显式事实，而不是隐藏状态。

### 7.22 TASK-085：Simple Battery Physics Model

PV 和 Load profile model 只回放事实；Battery model 首次引入真正的状态转移。`SimpleBatteryPhysicsModel` 接收 exact source
state、actuation、step duration 和 immutable `BatteryParameters`，输出 actual power 与 next SOC。

```text
source SOC + requested Battery power + duration + parameters
        |
        v
SimpleBatteryPhysicsModel
        |
        +-- actual Battery power
        `-- immutable next SOC
```

Battery power 继续使用统一符号：正值充电、负值放电、零为空闲。充电时，进入系统边界的能量乘以 charge efficiency 后才成为
stored energy；放电时，为向系统边界提供指定能量，stored energy 的减少量需要除以 discharge efficiency。

```text
charge:    ΔE_stored = +P * Δt * η_charge
discharge: ΔE_stored = -|P| * Δt / η_discharge
SOC_next = SOC_source + ΔE_stored / capacity
```

actual power 同时受充放电功率上限和 SOC headroom 限制。充电不超过 SOC 1.0，放电不低于 reserve SOC。如果输入状态已经低于
reserve，model 只阻止继续放电，不会把 SOC 凭空抬高到 reserve。无实际变化时保留 exact source-state identity；有变化时创建
新的 immutable state。

这不等于把 Constraint 搬进 Battery model。上游 Constraint 判断意图是否可行；simulation physics 负责保证明确 actuation 在
其物理模型中不会产生非法状态，并报告真正实现的功率。model 不生成 intent，不知道 EMS objective，也不控制真实 BMS/PCS。

### 7.23 TASK-086：Grid Energy Balance Model

TASK-086 使用 PV、Load 与 Battery 的 actual results 计算同一步 Grid exchange。首先必须把符号放在同一个坐标系中：

```text
Battery > 0: charging
Battery < 0: discharging
Grid > 0: import
Grid < 0: export
```

因此正确平衡是：

```text
Grid = Load + Battery - PV
```

充电是额外用电，所以增加 Grid import；放电向系统供能，所以减少 Grid import。最初草案中的 `Load - Battery - PV` 与上述
符号冲突，已在实现前纠正。

`GridEnergyBalanceSimulationModel` 保存同一步 exact PV/Load/Battery result references，并使用 identity 检查它们共享同一个
step。它使用 Battery `actual_power_kw`，而不是 actuation request，因为 TASK-085 可能因 power/SOC limits 调整实际功率。

Grid result 仍保存 exact `GridSimulationInput`，但 `requested_grid_power_kw` 不是 balance 的事实来源。model 是 per-step immutable
evaluation configuration，不保存 history 或 current state。未来 runner 负责先取得同一步 component results，再显式调用 Grid
balance；TASK-086 不修改既有 executor 或 scenario contracts。

## 8. 学习建议

建议按以下顺序理解 EOS：

1. 先阅读不可变 dataclass、单位和符号约定；
2. 追踪一个 `EnergySystemState` 如何被装配成 `DecisionContext`；
3. 区分 `DecisionIntent` 与设备 `Command`；
4. 理解 policy 与 constraint 为什么是两个接口；
5. 用对象身份关系阅读 cycle 和 explanation；
6. 最后研究 runtime、journal、replay 与 legacy execution。

学习具体 EMS 算法时，始终回答四个问题：

- 使用了哪些事实？
- 产生了什么语义意图？
- 哪些安全约束不属于策略？
- 谁最终负责设备执行和失败处理？

### 7.24 TASK-087：24 小时 Simulation Runner

TASK-087 把前四个 concrete simulation models 组合为第一个可运行的 24 小时 Demo：

```text
DailySimulationScenarioInput
        |
        v
PV / Load facts -> simple Battery request
        |
        v
Battery physics -> realized Battery power and next SOC
        |
        v
Grid balance -> SingleStepSimulationExecutor -> Trace
        |
        v
DailySimulationResult
```

这里最重要的学习点是“连续执行”不等于引入 Runtime。24 个 step 的 identity、timestamp
和顺序全部由 caller 提供；runner 不读取 clock，也不生成未来时间。每一步只通过 Phase 7
executor 一次，完成后把 exact Battery next state 作为下一步 source state。23 个显式
progression artifacts 记录这个关系，因此 SOC continuity 不是只比较数值，而是可以追踪对象
provenance。

Demo rule 只用于验证 simulator：PV surplus 请求充电，PV deficit 且 SOC 高于 reserve 时请求
放电。Battery model 决定实际可实现功率并保护 SOC；Grid model 使用 realized Battery power，按
`Grid = Load + Battery - PV` 计算 exchange。这保持了 strategy、physics 与 evidence 的职责分离。

Grid 依赖同一步已完成的 PV/Load/Battery results。Runner 不修改 Phase 7 executor，而是先显式
协调 results，再通过 frozen exact-result adapters 让 executor 聚合 exact evidence。Adapters
不重算、复制或规范化结果。最终 `DailySimulationResult` 保存 exact source、scenario、traces
和 progressions，但不拥有 Runtime history、Scheduler、Device 或 Command。

### 7.25 TASK-088：Simulation Result Export

仿真完成并不等于工程人员能够方便地使用结果。TASK-088 在 completed
`DailySimulationResult` 上增加只读 output layer：

```text
DailySimulationResult
        |
        +--> deterministic CSV
        +--> Power / SOC SVG
        `--> DailyEnergySummary
```

CSV 的每一行对应一个 exact trace，固定包含 timestamp、PV、Load、Battery、Grid power
和 SOC。它不从输入 curve 重新计算结果，而是读取 model 已经实现的 realized values。Power
图也同时展示这四条曲线，SOC 图展示每一步完成后的 next-state SOC。

功率是瞬时 kW，能量是对显式 step duration 的积分，单位 kWh。Battery throughput 使用
绝对 Battery power，因此充电和放电都会贡献 throughput；Grid import 只积累正 power，
Grid export 把负 power 的绝对值作为正的 export energy 报告。

Output artifacts 保存 exact `DailySimulationResult` reference，但绝不修改 result、trace
或 state。相同 result 生成 byte-identical CSV/SVG。文件写入仅面向 caller 提供的 existing
directory，不等于数据库 persistence、Runtime history、dashboard 或 real-time monitoring。

## 9. 文档维护规则

以后每完成一个 TASK：

1. 更新本手册中新增或变化的业务概念；
2. 更新 `EOS_架构说明.md` 中的边界、包职责和依赖方向；
3. 在 `TASK演进记录.md` 中追加目标、实现、意义、文件、验证和关键决策；
4. 不用文档“宣布”尚未落地的能力；
5. 不为解释方便而改变已经 review 通过的代码契约。
