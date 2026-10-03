# 零上网与弃光验证矩阵（设计阶段）

本矩阵用于后续实现验收，目前不对应生产代码。符号固定为：PV available `A`、PV
utilized `U`、curtailed `C`、load `L`、battery actual `B`（正充负放）、grid `G`
（正进口负出口）、export limit `E`。默认一小时，弃光已授权，所有数值单位为 kW。

| ID | 显式输入 | 独立 expected | 判定重点 |
| --- | --- | --- | --- |
| Z01_IMPORT_ONLY | A=0, L=2, B=0, E=0 | U=0, C=0, G=+2 | 进口不受零上网误伤 |
| Z02_BALANCED_PV | A=2, L=2, B=0, E=0 | U=2, C=0, G=0 | 无需弃光 |
| Z03_ALLOWED_EXPORT | A=3, L=1, B=0, E=2 | U=3, C=0, G=−2 | 等号边界允许 |
| Z04_LIMITED_EXPORT | A=4, L=1, B=0, E=2 | U=3, C=1, G=−2 | 非零 export limit 仍受约束 |
| Z05_CHARGE_ABSORBS_SURPLUS | A=5, L=2, B=+3, E=0 | U=5, C=0, G=0 | 只读取已有 battery actual |
| Z06_CHARGE_LIMIT_CURTAIL | A=10, L=1, B=+3, E=0 | U=4, C=6, G=0 | 不虚构超过 3 kW 充电 |
| Z07_S09_FULL_BATTERY | A=10, L=0, B=0, E=0 | U=0, C=10, G=0 | 满 SOC 时全部弃光，不伪造吸收 |
| Z08_DISCHARGE_SERVES_LOAD | A=0, L=3, B=−2, E=0 | U=0, C=0, G=+1 | 负 B 口径与负载服务 |
| Z09_DISCHARGE_TO_LIMIT | A=1, L=3, B=−3, E=1 | U=1, C=0, G=−1 | 放电但未超过允许出口 |
| Z10_NON_PV_EXPORT | A=0, L=0, B=−1, E=0 | REJECTED | 弃光无法修正电池造成的出口 |
| Z11_NO_CURTAIL_AUTH | A=10, L=0, B=0, E=0, permission=false | REJECTED | 不得静默弃光或允许出口 |
| Z12_PARTIAL_HEADROOM | A=2, L=0, B=+0.526315789474, E=0 | U=0.526315789474, C=1.473684210526, G=0 | 使用电池模型实际限幅值 |
| Z13_DURATION_ENERGY | Δt=0.5, A=4, L=1, B=+1, E=0 | U=2, C=2；available=2 kWh, utilized=1 kWh, curtailed=1 kWh | 功率与能量 oracle 分离 |
| Z14_ZERO_VALUES | A=L=B=E=0 | U=C=G=0 | 全零合法且确定 |
| Z15_IDENTITY_MISMATCH | PV/Load/Battery step identity 不同对象 | 构造或 evaluate 拒绝 | 值相等不能替代 exact identity |
| Z16_INVALID_NUMERIC | A/L/E 为负、NaN/∞，B 为 NaN/∞ | 构造拒绝 | fail closed；bool/string 也拒绝 |

## 每个 SATISFIED 场景必须共同断言

1. `A = U + C`；
2. `G = L + B - U`；
3. `G >= -E`；
4. `0 <= U <= A` 且 `C >= 0`；
5. exact source input、step identity、ZeroExport feasibility、PV input、Load result 和
   Battery result identity 全部保留；
6. 原 PV available、load、battery result、decision/provenance/feasible/handoff 均未改写；
7. CSV/JSON 分开输出 available/utilized/curtailed/battery/grid/status/reason，并标记
   `SIMULATED`。

## 每个 REJECTED 场景必须共同断言

- 不创建声称合规的 PV/Grid result；
- 不复用旧 step 的 feasibility、Battery result 或 assessment；
- 不把 rejected 写成 idle、PASS、设备 ACK 或已发生的弃光；
- 异常/拒绝原因稳定、机器可读，原输入保持可审计。

## 后续最小测试分层

- 纯合同单元测试：Z14–Z16 与 immutable/exact identity；
- 独立算术单元测试：Z01–Z13，expected 使用手写常量；
- Simulator 组合测试：curtailment-aware PV result → 现有 Grid balance；
- 日 runner 回归：弃光已授权时 S09 从 LIMITATION 变为 PASS；确认其他 17 场景、
  纯价格套利和 forecast limitation 分类不变；
- 静态检查及必要 full regression 只在实现阶段运行，本设计阶段不运行全套。
