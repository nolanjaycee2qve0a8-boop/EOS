# 虚拟家庭储能缺陷查找 Campaign 合同

本 Campaign 以本地提交
`6785e5f2d569e93f0524e19cb0a4d3aa6e2ec334` 为不可覆盖的 24 小时教学基线。
它只新增隔离的仿真场景、独立复算、测试和报告，不修改冻结的 EMS、优化、
Simulator、ledger、Edge 或治理实现。

## 目的与边界

- 运行少量有判别力的确定性场景，寻找策略局限、模拟器/组合缺陷、输入合同拒绝
  和既有测试缺口。
- 复用现有 Schedule/Economic 日 runner、显式 Forecast、Feasibility、
  ActuationHandoff、Simulator 实际 SOC 反馈和 ledger。
- 每个可执行路径独立复算功率平衡、SOC、购售电能量、进口成本、出口收益和退化
  成本；oracle 只读取最终 trace 和显式输入，不调用被测 ledger/教学汇总公式。
- 输出固定场景矩阵、逐路径 CSV/JSON、发现 CSV/JSON、简短中文报告和一个只突出
  异常的静态 SVG。所有输出标为 SIMULATED。
- 输入拒绝场景要求在任何日 runner 执行前 fail closed，并记录异常类型与文本。

本 Campaign 不接实物、HIL、PCS/BMS、协议、网络、后台服务、Edge `PowerCommand`
或真实电价。软件 PASS 只证明这些固定仿真不变量成立，不证明设备可用性。

## 既有覆盖与新增选择

- Campaign B：72 格 PCS/SOC/常规 TOU/会计敏感性；不重复其普通扫参。
- Campaign C：39 个 perfect、±25% 和 ±2h 预测误差；只新增完全错报的突发事件。
- Campaign D：4×7 天和 2×30 天状态延续；只新增一个两日跨午夜最小链。
- 24 小时教学示例：固定 reference 日与四个关键小时；新增精确阈值和极端输入。

## 判定规则

`PASS` 表示实际行为满足显式合同与物理/会计不变量。`FAIL` 表示可复现的软件
不变量违例。`LIMITATION` 表示代码按当前合同运行，但产品能力缺失或策略范围有限；
不能把它改写成 PASS。`REJECTED_AS_EXPECTED` 表示无效输入在执行前被合同拒绝。

冻结核心的任何 `FAIL` 或 `LIMITATION` 只形成最小复现和修复建议；本批不修改核心
算法，也不为让场景通过而改变 expected。
