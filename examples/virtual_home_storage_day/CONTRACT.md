# 24 小时虚拟家庭储能教学合同

本示例基于 main `c1956b407c5ea8269182dd96d37936e2f52a666b`，只新增
`examples/virtual_home_storage_day/`、对应测试、中文指南与 README 入口。它不修改
Residential EMS、Simulator、优化、经济账本、Edge 或治理实现，也不改变 PR #220
已有五场景教学示例。

## 范围

- 只调用一次现有 `run_residential_reference_demo`，使用其固定 24 × 1 小时虚拟
  PV、家庭负载、分时电价、10 kWh 电池、50% 初始 SOC 与 perfect-forecast 输入。
- 教学主路径选择既有 Economic 路径；它实际经过 Forecast、现有 MPC/Strategy、
  CurrentAction、EMSDecision、Feasibility、Actuation、Simulator 和实际 SOC 反馈。
- 从该次调用返回的真实 trace/ledger 生成一个中文逐小时 CSV、JSON、关键事件文本、
  日汇总，以及 PV、负载、电池、购电、售电、SOC 共用时间轴的静态 SVG。
- 保留 reference demo 原始输出，便于追溯 Schedule/Economic 两条现有路径；包装层
  不重新运行、复制或重建控制算法。

## 语义

功率采用既有 Simulator 约定：电池正值为充电、负值为放电；电网正值为购电、
负值为售电。图表将电网功率拆成非负的购电与售电两条曲线，但逐小时记录同时保留
原始 signed grid power。所有步长为 1 小时，能量按实际功率乘以实际 duration 积分。

价格有两种已存在的真实作用：Economic 路径在低价、无 PV 盈余的候选时段计算并
限制有经济支持的电网充电；完成仿真后 ledger 用每小时进口电价核算实际购电成本。
PV 充电、放电和 idle 可绕过该低价充电 gate。出口电价、退化费率、终端估值仅是
reference demo 的显式会计假设；本示例不声称优化收益或适用于真实电价。

中文解释直接保留现有 `zh-CN` 决策 formatter 的候选、最终 action、物理修订与约束
原因，并补充逐小时输入、FeasibleDecision、Actuation、Simulator actual 和 ledger
结果。它是对已有事实的教学展示，不创建 Edge PowerCommand，不接入 P0.2–P0.7
虚拟 PCS/BMS session，也不把仿真 actuation 说成设备命令。

## 验收与边界

测试独立核对 24 个连续时间点、1 小时步长、功率平衡、SOC 能量积分、SOC/功率
约束、ledger 成本积分、decision/provenance/feasibility/handoff identity、图表点数、
中文解释与稳定导出。expected 使用手算关系与固定输入，不调用包装层公式自证。

所有数据和输出必须标为 simulated。无实物、协议、网络、HIL、PCS/BMS 控制、PWM、
电流环、母线动态、硬件保护、实时循环、凭据或部署。预测为完美固定输入，不证明
天气或预测误差鲁棒性；既有 Campaign C–F 报告继续承担预测误差/多日研究，本示例
不复制它们。完成后只形成本地审核候选，不 push、PR 或 merge。
