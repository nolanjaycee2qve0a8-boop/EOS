# EOS Phase 5 Decision Formation Architecture v1.0

## 1. Phase 背景与目标

Phase 4 建立了 Objective 与 Capability 的描述、Discovery、Matching、Activation 和 Composition
证据边界，但刻意没有产生 `DecisionIntent`。Phase 5 负责在不连接 Runtime 或设备的前提下，定义
“业务证据如何形成、解析并约束为一个可行语义意图”。

Phase 5 v1.0 的目标是冻结 Decision Formation 的合同语言，而不是实现 EMS 算法：

- 用 `charge`、`discharge`、`idle` 表达设备无关的语义 Intent；
- 记录 Context、Objective/Capability composition 与 Candidate provenance；
- 将多个 Candidate 的 Resolution 与 Formation 分离；
- 将 source intent 与 feasible intent 的生命周期分离；
- 保持 immutable contract、exact identity 和单向依赖。

## 2. TASK-061～064 总结

| TASK | 主题 | 核心产物 | v1.0 状态 |
| --- | --- | --- | --- |
| TASK-061 | DecisionIntent Contract | `DecisionIntent(action)` | 已实现并合并 |
| TASK-062 | Decision Formation Boundary | Formation Input、Candidate、abstract Boundary | 设计和独立实现审查完成；合并状态由对应 PR 决定 |
| TASK-063 | Intent Resolution Boundary | Resolution Input、Result、abstract Boundary | 架构草案审查通过，未实现算法 |
| TASK-064 | Constraint Evaluation Boundary | Evaluation Input、Result、abstract Boundary | 架构草案审查通过，未实现具体约束 |

该表区分“批准设计”与“当前 `main` 已有生产实现”。本文档不会把 TASK-063/064 描述为已经存在的
Python API。

## 3. 最终架构链

```text
DecisionContext
        +
ObjectiveCapabilityActivationComposition
        +
exact active CapabilityDescriptor
        |
        v
DecisionFormationInput
        |
        v
DecisionFormationBoundary
        |
        v
DecisionIntentCandidate tuple
        |
        v
DecisionIntentResolutionInput
        |
        v
DecisionIntentResolutionBoundary
        |
        v
DecisionIntentResolutionResult
        |
        v
Source DecisionIntent
        |
        v
DecisionConstraintEvaluationInput
        |
        v
DecisionConstraintEvaluationBoundary
        |
        v
DecisionConstraintEvaluationResult
        |
        v
Feasible DecisionIntent
        |
        v
Future Phase 6 Simulation Observation
```

该链路是设计顺序，不是 Runtime execution flow。Boundary 不拥有 scheduler、clock、thread、device 或
持久化状态。

## 4. DecisionIntent Contract

Phase 5 使用独立的：

```text
decision_formation.DecisionIntent
└── action: charge | discharge | idle
```

Action 只表示“希望做什么”，不表示：

- 电池功率数值；
- 正负功率方向；
- PCS/BMS setpoint；
- CAN/Modbus frame；
- Command 或执行结果。

因此 `DecisionIntent != Command`。现有 Phase 3
`kernel.decision.DecisionIntent(battery_power_intent_kw)` 保持隔离，没有 inheritance、adapter、alias
或自动转换。

## 5. Formation Boundary

Formation Input 由三份 exact evidence 组成：

- `source_context`；
- Objective/Active-Capability composition；
- composition active tuple 中的 exact Capability descriptor。

Formation Candidate 保存 exact Input 与 exact Intent。Descriptor 只证明来源，不等于 Capability
implementation、factory 或 registry key。Formation 不选择 Capability，也不包含 charge/discharge
业务规则。

## 6. Resolution Boundary

Resolution Input 保存 caller 提供的 Candidate tuple，不排序、不去重、不复制。Resolution Result 保存：

- exact Resolution Input；
- exact source Candidate；
- exact source Intent。

核心关系：

```text
result.source_candidate is one exact input candidate
result.source_intent is result.source_candidate.intent
```

通用 Resolution contract 不包含 priority、ranking、score、weight、默认 first/last candidate 或 conflict
resolution algorithm。

Phase 5 Resolution 与 Phase 3 `capability.IntentResolutionBoundary` 独立，不迁移、不适配、不复用其
具体实现。

## 7. Constraint Evaluation Boundary

Constraint Evaluation 将 source intent 与 feasible intent 明确分开：

```text
source_intent   = Resolution 选出的业务意图
feasible_intent = Constraint Evaluation 允许继续传递的语义意图
```

未调整时：

```text
feasible_intent is source_intent
```

受到约束时，可以产生新的 immutable `idle` intent，但不能修改 source intent。Phase 5 action 的合法
收敛关系是：

```text
charge    -> charge | idle
discharge -> discharge | idle
idle      -> idle
```

Constraint 不允许 charge/discharge 相互反转，也不能从 idle 创造动作。这保证 Constraint 只限制可行性，
不会偷偷成为 Decision Formation。`feasible_intent` 必须是 `DecisionIntent`，不能使用 `None` 表示
不可行。

Phase 5 Constraint Evaluation 与 Phase 2 `DecisionConstraintBoundary`、`FeasibleDecisionIntent` 和
Constraint Pipeline 保持隔离。

## 8. Identity 与 Provenance

Phase 5 使用 direct-boundary identity contract。每个 boundary 只保证自己的直接输入输出关系，不声称
存在跨 Phase 4/5 的自动执行链。

```text
formation_input.source_context is original_context
formation_input.composition is original_composition
formation_input.capability is original_active_capability

candidate.formation_input is original_formation_input
candidate.intent is original_intent

resolution_result.source_candidate is one exact input candidate
resolution_result.source_intent is resolution_result.source_candidate.intent

evaluation_input.resolution_result is original_resolution_result
evaluation_input.source_intent is resolution_result.source_intent

evaluation_result.evaluation_input is original_evaluation_input
evaluation_result.source_intent is evaluation_input.source_intent
```

禁止 copy、deepcopy、serialization/deserialization、value-only reconstruction、normalization 和隐式
conversion。

## 9. Objective、Capability、Intent 与 Constraint 边界

| Layer | 回答的问题 | 不回答的问题 |
| --- | --- | --- |
| Objective | EMS 关心什么 | 应充电还是放电 |
| Capability Descriptor | 哪种能力与证据相关 | 如何执行该能力 |
| Formation | 哪些 exact evidence 与候选 Intent 相关 | 哪个 Candidate 获胜 |
| Resolution | 哪个 Candidate 成为 source provenance | 物理上是否可行 |
| Constraint Evaluation | source action 是否保持或收敛为 idle | 应生成什么新策略 |
| Command/Execution | 未来如何执行 | 不属于 Phase 5 |

Objective 不直接生成 Intent；Capability Descriptor 不等于 implementation；Constraint 不生成业务策略；
Optimization 不等于 Decision。

## 10. Dependency Direction

允许方向：

```text
decision_formation.intent

decision_formation.formation
    -> stable Context / Objective composition / Capability descriptor contracts

decision_formation.resolution
    -> formation candidate / semantic intent

decision_formation.constraint_evaluation
    -> resolution result / semantic intent
```

禁止反向依赖和以下 production dependencies：

- Capability implementation；
- concrete Constraint implementation；
- Optimization；
- Runtime、Execution、Dispatch；
- Command、Device、PCS、BMS；
- CAN、Modbus、MQTT；
- persistence、telemetry、cache、history。

## 11. Phase 5 Non-goals

Phase 5 v1.0 不实现：

- concrete Formation algorithm；
- candidate selection、priority、ranking、scoring 或 weighting；
- optimization、forecasting 或 scheduling；
- SOC、电池模型、功率限制、Grid/PCS/Device constraint；
- feasible intent 到 Command 的转换；
- Runtime loop、dispatch、device control；
- persistence、telemetry 或 replay migration；
- legacy Phase 3/Runtime 路径迁移。

## 12. Phase 6 仿真衔接

Phase 6 可以在不连接真实设备的前提下，以测试或 simulator-owned fixtures 构造 Phase 5 artifacts，验证：

- 多个 Candidate 的 provenance 是否完整；
- concrete resolver 是否遵守公开规则和 exactly-once semantics；
- Constraint 是否只做单向可行性收敛；
- source/feasible identity 是否符合合同；
- 相同输入是否产生确定性观察结果。

Phase 6 仿真不能被描述为 Runtime 或 Device execution。它不得提前引入 PCS/BMS、CAN/Modbus、真实
Command dispatch、Optimization solver 或持久化。若未来需要 executable simulation lifecycle，必须由
独立 TASK 和 ADR 定义其 input、result、clock ownership、failure boundary 与 replay semantics。

## 13. v1.0 结论

Phase 5 v1.0 已完成 TASK-061～064 的架构语言设计：semantic Intent、Formation provenance、Candidate
Resolution 和 Constraint Evaluation 生命周期已经分离。当前完成的是稳定设计基线，不是完整 EMS
执行系统，也不代表所有设计合同均已合并为生产代码。
