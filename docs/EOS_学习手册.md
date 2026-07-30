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

EOS 当前只提供电价事实与策略扩展边界，尚未实现 TOU 策略、调度或优化。

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

### 4.8 FeasibleDecisionIntent

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

### 4.9 ConstraintExplanation

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

### 4.10 DecisionEvaluationCycle

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

### 4.11 DecisionEvaluationOrchestrator

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

## 5. 学习建议

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

## 6. 文档维护规则

以后每完成一个 TASK：

1. 更新本手册中新增或变化的业务概念；
2. 更新 `EOS_架构说明.md` 中的边界、包职责和依赖方向；
3. 在 `TASK演进记录.md` 中追加目标、实现、意义、文件、验证和关键决策；
4. 不用文档“宣布”尚未落地的能力；
5. 不为解释方便而改变已经 review 通过的代码契约。
