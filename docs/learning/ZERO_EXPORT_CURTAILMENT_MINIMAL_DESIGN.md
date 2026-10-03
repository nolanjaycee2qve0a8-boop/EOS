# 零上网与 PV 弃光最小合同及隔离 opt-in 实现

## 1. 范围与目标

本设计承接缺陷 Campaign 的 S09：`export_limit=0`、PV=10 kW、负载=0、SOC=100%
时，现有日链仍输出 10 kW 上网。本轮只定义一个虚拟仿真合同和验证矩阵，不修改
策略、feasibility、handoff、Simulator、runner 或设备接口。

经评审确认后，合同已在
`examples/virtual_home_storage_zero_export/correction.py` 作为隔离、显式 opt-in 示例
实现。默认 runner 和本文件分析的现有生产合同仍未修改。

目标是在每个显式仿真步内：

- 保留 PV 可用功率、PV 实际利用功率与弃光功率三个不同事实；
- 满足 caller 给定的 `export_limit_kw`，包括严格零上网；
- 使用现有电池模型已经算出的虚拟实际功率，不虚构额外充电能力；
- 保持负载完整供电，允许现有模型从电网进口；
- 当仅靠 PV 弃光无法满足限制，或 caller 未批准弃光时，fail closed；
- 不增加纯价格套利、forecast guard、真实 PCS/BMS 或现场控制含义。

## 2. 现有接口结论

### `ZeroExportBoundary` 保持只读事实

现有 `ZeroExportBoundary` 位于 `EMSDecision + exact DecisionProvenance` 之后，只返回
`ZeroExportFeasibility(source_decision, source_provenance, is_feasible)`。TASK-096 明确
禁止它修正功率、替换 action、生成 actuation 或执行控制。因此新实现不得向该类型塞入
corrected power 或 curtailment 字段，也不得把 `is_feasible=True` 解释为物理完成。

它可以作为 correction 输入中的 exact lineage/precheck 事实，但不能单独证明经过电池
SOC/功率裁剪后的最终 Grid 功率合规。

### 现有 `FeasibleDecision` 不适合承载零上网纠偏

`FeasibleDecision` 只允许保留源 action 或降为 idle，不能把 idle/discharge 反转为
charge，也不能为吸收 PV 而增加源请求。`ActuationHandoffResult` 又要求 actuation 与该
feasible action/power 完全一致。为本功能放宽它们会改变既有策略与 handoff 语义，超出
最小范围。

因此第一版采用 **curtailment-only**：不修改电池 action 或功率，只在电池虚拟物理
结果已知后减少 PV 实际利用量。未来若产品要求“先额外充电、再弃光”，应另立 battery
correction 合同和审批，不在本设计中暗含。

### PV 与 Grid 已有的表达能力

- `PVSimulationInput.available_power_kw` 已表示不可改写的可用 PV。
- `PVSimulationResult.actual_power_kw <= available_power_kw` 已能表示利用后的 PV，但当前
  `PVProfileSimulationModel` 总是令 actual=available，没有弃光决策来源。
- `GridEnergyBalanceSimulationModel` 使用
  `grid = load + battery - pv`，其中 Grid 正为进口、负为出口；电池正为充电、负为放电。

隔离示例新增独立 correction evidence，再由 curtailment-aware PV 结果把
`pv_utilized_kw` 写入新的 `PVSimulationResult`。不得改写 daily PV curve、原
`PVSimulationInput`、历史 decision/context 或 Battery result。

## 3. 已实现的最小合同

示例实现采用以下合同：

```text
ZeroExportCurtailmentInput
  exact_zero_export_feasibility
  exact_expected_provenance          # caller 所属策略/decision 的 exact lineage
  exact_source_handoff               # actuation 必须属于本 source step
  exact_pv_input                    # available PV 与 step identity
  exact_load_result                 # 虚拟实际负载
  exact_battery_result              # 现有 SOC/效率/功率约束后的虚拟实际功率
  exact_grid_input                   # exact step identity；不改写 requested 值
  export_limit_kw                   # 有限非负；0 表示零上网
  curtailment_permission            # caller 显式批准或禁止

ZeroExportCurtailmentEvidence
  exact_source_input
  pv_available_kw
  pv_utilized_kw
  pv_curtailed_kw
  battery_actual_power_kw
  load_served_kw
  resulting_grid_power_kw
  export_limit_kw
  status                            # SATISFIED / REJECTED
  reason_code
  *_energy_kwh                      # available/utilized/curtailed/load/battery/grid
```

所有 source/result 必须共享 exact `SimulationStepIdentity`；输入和输出 immutable、
slotted、无 cache/clock/history。`load_served_kw` 必须等于 exact load result，第一版不做
load shedding。`battery_actual_power_kw` 必须等于 exact battery result，禁止重新计算或
扩大电池吸收量。

建议 reason code 最小集合：

- `WITHIN_EXPORT_LIMIT`：无需弃光；
- `PV_CURTAILED_TO_EXPORT_LIMIT`：显式批准后弃光；
- `CURTAILMENT_NOT_AUTHORIZED`：需要弃光但 caller 未批准；
- `NON_PV_EXPORT_CANNOT_BE_CORRECTED`：即使 PV 利用为零，电池放电仍导致超限出口。

identity、数值或 lineage 不一致在 input/evidence 构造时直接拒绝，不生成伪造的业务
reason code。

`REJECTED` 证据只是 fail-closed 结果，不得继续创建该步的 PV/Grid result、handoff 或
设备命令。虚拟 Battery result 可作为求值输入，但不代表真实电池已经动作。

`OptInZeroExportStepExecutor` 先通过现有纯电池/负载模型生成不可变 preview；只有
correction 为 `SATISFIED` 才用 exact preview 组装完整 `SimulationExecutionTrace`。
`REJECTED` 返回 `simulation_trace=None`，caller 无 next SOC、progression 或 ledger
可以提交。

## 4. 独立公式与不变量

对一个持续 `Δt` 小时的显式步，定义：

- `A >= 0`：PV available kW；
- `U >= 0`：PV utilized kW；
- `C >= 0`：PV curtailed kW；
- `L >= 0`：完整服务的 load kW；
- `B`：现有电池模型的 actual kW，正充电、负放电；
- `G`：Grid kW，正进口、负出口；
- `E >= 0`：允许的最大出口 kW。

必须满足：

```text
A = U + C
G = L + B - U
G >= -E
0 <= U <= A
C >= 0
```

在 curtailment-only 方案中，可利用 PV 上限为：

```text
U_limit = L + B + E
```

- 若 `U_limit < 0`，即使 `U=0` 仍有 `G < -E`，出口由电池放电造成；必须
  `NON_PV_EXPORT_CANNOT_BE_CORRECTED`。
- 否则 `U = min(A, U_limit)`，`C = A - U`，`G = L + B - U`。
- 若 `C > 0` 且未显式批准弃光，必须 `CURTAILMENT_NOT_AUTHORIZED`，不得偷偷允许出口。
- 能量 oracle 独立检查 `AΔt = UΔt + CΔt` 与
  `GΔt = LΔt + BΔt - UΔt`；不得调用被测 helper 生成 expected。

电池约束仍完全由现有 `SimpleBatteryPhysicsModel` 负责：

```text
B_charge <= min(P_charge_max, (1-SOC) * capacity / (Δt * η_charge))
abs(B_discharge) <= min(P_discharge_max,
                        (SOC-reserve) * capacity * η_discharge / Δt)
```

correction 只读取 `B`，不重新应用这些公式，也不能用理论 headroom 替换实际结果。

功率与能量对账使用公开常量 `POWER_TOLERANCE_KW=1e-9` 和
`ENERGY_TOLERANCE_KWH=1e-9`。该容差只接受边界浮点残差；超过容差的出口必须实际
弃光或拒绝，不能用容差吞掉。`BΔt` 是现有 Simulator 公共电气功率边界上的有符号
交换能量；电池内部充放电效率只体现在既有 Battery next-SOC 中，本示例不声称真实
AC/DC 拓扑或另加变流损耗。

## 5. S09 最小复现

固定输入：`A=10`、`L=0`、`SOC=100%`、`E=0`。即使策略请求充电，现有电池物理
结果也因无 SOC headroom 得到 `B=0`。

```text
U_limit = 0 + 0 + 0 = 0 kW
U = min(10, 0) = 0 kW
C = 10 - 0 = 10 kW
G = 0 + 0 - 0 = 0 kW
```

因此合规结果只能明确记录 `pv_available=10`、`pv_utilized=0`、`pv_curtailed=10`、
`battery_actual=0`、`grid=0`。把 10 kW 写成电池充电或把 available PV 改成 0 都是
伪造；继续输出 `grid=-10` 则违反零上网合同。

## 6. 不在本批设计中的行为

- 不因价格信号新增充放电或对网套利；
- 不用 realized 值全面推翻 forecast 策略，只处理显式出口约束；
- 不改变现有 decision/provenance/feasible/handoff identity；
- 不定义 inverter、MPPT、无功、母线、电流环、PWM、保护、通信或现场 ACK；
- 不把模拟 `pv_curtailed` 描述为设备实测或真实电站弃光。

## 7. 已确认的实现取舍

1. **第一版纠偏策略**：采用 curtailment-only；“优先额外充电再弃光”会改变
   FeasibleDecision/handoff 语义，应另立范围。
2. **无弃光授权时的行为**：整步 fail closed，不生成 PV/Grid 结果；只保留 rejection
   evidence，不能称为零上网执行。
3. **`ZeroExportFeasibility` 的角色**：保留为 lineage/precheck，并要求 correction
   独立按 exact Battery/PV/Load 结果证明最终约束；不能只信 Boolean。
4. **`export_limit_kw > 0`**：同一合同统一支持，边界为 `G >= -E`，避免为零值写
   特例算法。
