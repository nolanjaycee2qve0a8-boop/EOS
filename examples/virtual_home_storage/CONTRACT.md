# 虚拟家庭储能：有界教学合同

本合同先于实现写入。用户已批准五个固定场景：充电、放电、功率限幅、
命令过期、ACK 失配；这是 example，不是新 P0 阶段或生产审批算法。
基线为 main `bc15c5ad7ec50a4b09d3fbec4f02d7f56bd0c5a8`。
只新增本目录、对应 integration tests、教学 guide 与必要入口链接。
冻结实现、P0.1–13 语义、治理原则、Residential EMS/Campaign A–F 均不修改。

## Why：看清五层不同的功率事实

真实调用 `SelfConsumptionStrategy.evaluate`，每场景创建新 EMSContext、
EMSDecision 和 DecisionProvenance。策略请求不是批准。调用方固定 approval
fixture 明确列出上下文、期望策略 action/magnitude、批准 action/magnitude；
只有逐项匹配才构造 FeasibleDecision。匹配检查仅保护教学 fixture 的适用范围，
不是完整自动生产 feasibility，也不是任意策略输出的 passthrough。

## How：有限、同步、显式

每场景新建 P0.2 虚拟 PCS/BMS，先用无命令的 1 秒启动 tick 进入 READY；
随后一次 60 秒受控 session cycle：P0.7 → P0.6 → P0.5 → P0.3 → P0.2/P0.1，
并由 P0.6 在 tick 后调用 P0.4 scripted adapter。没有后台循环或自动重试。
固定起点 2032-01-01T00:00:00Z，容量 10 kWh，初始 SOC 50%，边界 20–90%，
充放效率 0.9，BMS/PCS 充放上限均 3 kW；限幅场景 BMS charge derate 0.5，
于是 BMS 1.5 kW、PCS 3 kW。PV/load：充电及反例 4/1 kW，放电 1/4 kW，
限幅 7/1 kW。各 fixture 明确批准策略的 3、3、6 kW magnitude。
所有命令 ID、sequence、provenance、时间窗口由固定场景输入提供。

普通命令窗口从第 1 秒到第 121 秒；过期窗口为起点前 60 秒到起点。
ACK 失配发生在 P0.4：脚本 ACK 的 command ID 故意不同。
P0.4 observation/actual 是起点后第 1 秒的独立脚本快照（0 kW、50% SOC），
不是 P0.2 执行结果复制品；ACK accepted power 也只是显式脚本事实。

允许 demo-only 观察子类调用原实现一次并记录返回的不可执行 trace，以及 adapter
公开调用所得 facts；不替换算法、不 monkeypatch、不缓存 next-runtime 以绕过失败。
P0.4 ACK 失配使 session 终止且无 receipt/continuation，但已发生的 P0.3 tick
不会撤销。失败输出只能使用实际记录到的证据，未读取的 actual 标为 null。

## Tests：独立验收

用手算常量核对：60 秒充电 3 kW 储能增加 0.045 kWh，SOC 到 0.5045；
放电 3 kW 储能减少 1/18 kWh，SOC 到 0.49444444444444446；
限幅到 1.5 kW，增加 0.0225 kWh，SOC 到 0.50225。
检查真实调用 identity、每层一次调用、metadata 保真、过期拒绝施加、
P0.4 ACK 失配后的已执行事实、重复 decision/metadata/continuation 拒绝、
不使用 prior assessment 充当输入。补验 P0.2 ACK missing 不施加命令的模拟政策。
运行 focused、必要先修回归、完整 pytest 和仓库静态/pre-commit 门禁；
独立 fresh-context 只读 reviewer 在共享 executor 上重放反例及手算，不把共享机器
说成独立机器。保留初始失败记录，问题修复后复核。

## Output 与 limits

中文说明和 JSON/CSV 逐步表包含 request、fixture approval、command、safety limit、
virtual actual、SOC、P0.2 ACK/reconciliation、P0.4 独立 observation/ACK/actual、
停止/拒绝原因及固定输入。序列化只导出事实，不能恢复 session 或 execution authority。
所有输出标注 simulated；无真实采集、protocol/network、HIL、PWM、电流环、母线动态、
硬件保护、凭据或部署。ACK 缺失即不执行是 P0.2 模拟政策，现实设备可能已经执行。
不新增抽象 PASS/GAP 层，不做全天 MPC，不 push/PR/merge；停在审核完成候选。
