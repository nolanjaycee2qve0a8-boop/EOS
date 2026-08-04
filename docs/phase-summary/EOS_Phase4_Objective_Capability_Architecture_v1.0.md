# EOS Phase 4 Objective & Capability Architecture v1.0

## 1. Phase 背景

EOS Phase 1 建立 Decision Kernel，Phase 2 建立 Physical Constraint 与 Decision Evaluation
Framework，Phase 3 建立并冻结 EMS Capability Layer。进入 Phase 4 时，系统已经可以生成和
约束决策意图，但还缺少一套独立语言来回答：

- EMS 当前关心什么业务目标？
- 哪些 Capability descriptors 可以支撑这些目标？
- 哪些能力被报告 available、被 matched、被表达为 active？
- 这些关系如何保持 immutable identity lineage？

Phase 4 因此聚焦 Objective 与 Capability 的描述、关系和状态证据。它不实现决策或执行。

## 2. 完成内容

Phase 4 覆盖 TASK-053～TASK-059：

| TASK | Boundary / Artifact | 完成内容 |
| --- | --- | --- |
| TASK-053 | Objective Boundary | Objective descriptor 与 collection contract |
| TASK-054 | Objective Activation | Active Objective collection boundary |
| TASK-055 | Objective-Capability Mapping | Descriptor-level support relationships |
| TASK-056 | Capability Discovery | Available Capability descriptor observation |
| TASK-057 | Capability Matching | Matched relationships 与 explicit missing requirements |
| TASK-058 | Capability Activation | Active/inactive matched descriptor status |
| TASK-059 | Objective-Capability Activation Composition | Objective 与完整 active collection composition |

所有新增 production data models 均为 frozen/slotted；所有 collection 均为 tuple；所有边界均为
abstract/stateless，未引入 runtime ownership。

## 3. 架构演进

### 3.1 Phase 4 完整链路

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

该链路是 evidence progression，而不是 runtime execution pipeline。Phase 4 的对象只描述已经
提供的 descriptor、relationship 与 status facts。

### 3.2 状态语义演进

```text
Described Objective
        -> Active Objective

Mapped Capability Descriptor
        -> Available Capability Descriptor
        -> Matched / Missing Required Descriptor
        -> Active / Inactive Matched Descriptor
        -> Objective-Active-Capability Composition
```

每一步都保留前一步对象身份，避免用一个布尔值或空 tuple 混合多个不同语义。

## 4. 核心设计原则

### 4.1 Boundary First

Phase 4 先建立抽象边界和 immutable artifact，不创建具体 Discovery、Matching、Activation 或
Composition provider。未来实现只能插入边界，不能修改 Kernel 或已有 contract。

### 4.2 Descriptor Only

Objective 与 Capability relationships 停留在 descriptor 层。没有 Capability instance、factory、
Device handle 或 protocol frame 进入 Objective 架构。

### 4.3 Identity Preservation

Source collection、tuple、descriptor、match 和 composition references 都以 `is` 保持。值相等的
reconstructed descriptor 不能替代 source identity。

### 4.4 Immutable Contract

Frozen/slotted dataclass 防止字段重绑定，tuple-only collection 防止内部原地修改。两者共同构成
deep immutability contract。

### 4.5 Complete and Explicit State

- Required capability：必须明确 matched 或 missing；
- Matched capability：必须明确 active 或 inactive；
- Composition：保存完整 Active Capability Collection，不接受隐式 subset。

EOS 不用“没有出现在 tuple 中”同时表示 missing、inactive 和未处理。

### 4.6 Dependency Direction

允许的方向为 Objective package 依赖稳定 Capability contracts。Capability package 不依赖
Objective。两者均不依赖 Kernel Runtime、Execution 或 Device。

## 5. 已解决问题

### 5.1 Objective 与 Strategy 混合

通过独立 Objective descriptor，业务关注点不再只能隐藏在 Policy 分支或 Capability 名称中。

### 5.2 Availability、Matching 与 Activation 混合

三层独立后，系统可以区分“已报告可用”“满足需求关系”和“当前 active”三种事实。

### 5.3 Missing requirement 无法表达

TASK-057 首次审查发现只有 `matches` 无法表达明确 missing。新增 `missing_required` 与 complete
coverage contract 后，每个 required descriptor 都有唯一结果类别。

这一修复证明 CI 与测试通过不是架构审查的替代品。测试必须建立在完整可表达的模型之上。

### 5.4 Composition 隐式选择风险

TASK-059 不接受第二套 capability subset，而是保存 exact complete
`ActiveCapabilityCollection`，从结构上避免 composition 承担 selection。

## 6. 当前能力

Phase 4 完成后，EOS 可以：

- 不可变地描述 Objective；
- 表达 active Objective 集合；
- 在 descriptor 层表达 Objective-Capability support mappings；
- 观察 available Capability descriptors；
- 表达 matched relationships 和 missing requirements；
- 表达 matched capabilities 的 active/inactive 状态；
- 保存 Objective 与完整 active Capability evidence 的 composition；
- 对上述链路执行 identity、immutability 与 dependency architecture review。

Phase 4 当前不能：

- 生成 `DecisionIntent`；
- 选择、排名、评分或优化 Capability；
- 解决多个 Objective 或 Capability 的冲突；
- 调用 Runtime、Dispatcher、Device、PCS、BMS、CAN 或 Modbus；
- 持久化或遥测这些 artifacts。

## 7. 后续 Phase 5 路线

Phase 5 尚未实现。进入下一阶段前应先通过独立 TASK 冻结其目标和依赖方向。候选路线是研究
如何让已完成的 Objective-Capability evidence 被 Future Decision Layer 消费，同时保持：

1. Objective/Capability artifacts 不被修改；
2. 业务决策与物理 Constraint 继续分离；
3. 不把 selection、conflict resolution 或 optimization 隐藏进现有 Phase 4 boundaries；
4. Runtime 与 Device 仍只消费稳定输出，不反向拥有 Objective/Capability state；
5. 所有新关系继续保留 exact identity，并具备完整失败状态。

Phase 5 的具体 boundary、algorithm 和 integration contract 必须由后续任务单独提出、实现和审查。
本报告不宣布这些能力已经存在。

## 8. Phase 4 冻结结论

TASK-053～TASK-059 已形成一套完整的 Objective & Capability Architecture：目标可描述、能力可
发现、需求可匹配、缺失可表达、状态可激活、关系可组合，并且全过程保持 immutable identity
lineage。

Phase 4 的冻结范围是 architecture contracts 与 evidence models。Decision、Optimization、
Runtime 和 Device Integration 均明确留在范围之外。
