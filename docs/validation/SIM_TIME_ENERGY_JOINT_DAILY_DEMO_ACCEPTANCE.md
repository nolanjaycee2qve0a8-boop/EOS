# 独立 UTC 日联合入口：实施前验收合同

最新代码验收：**PASS**。定向134、相关158、Campaign62通过；最终文件冻结后pre-commit四hook全部Passed、整体exit 0，pytest **3046 passed、0失败/错误/跳过**。独立只读代码/覆盖KEEP。此前65/9、80/7及首次pre-commit文件变动保护失败完整保留，不覆盖或改写。本文记录于本地提交/恢复之前，后续精确提交与恢复结果以D盘独立回执为准；不表示已推送或设备验收。

基线：`34793256a8cdac2362d96a4ef630862c18afcd03`。2026-10-13 用户授权方案 A及后续最小坐标修复；仅八文件及评审文档状态。先验合同在代码和测试前写定，后文按时间追加真实结果。未发布。

权威输入为同目录 `SIM_TIME_ENERGY_JOINT_DAILY_INTEGRATION_REVIEW.md` v2，实施前 SHA256 `1E94BF13A5154435375E2CB0F90B27C6D1E7E9A4225C4B8E0CDDBE265D05CD4E`。其完整第 7 节 T1–T16 输入、预期、反例和停止条件纳入本合同，不能按测试结果调整。D 盘本轮根目录：`D:\项目数据\EOS\runs\joint-daily-20261013-e970e099d29f489398e7813e85793bec`；preflight 保留两份原探针与 v2 合同的精确副本和哈希。

## 冻结口径

UTC 2026-01-01 00:00 至次日 00:00（北京时间 08:00 至次日 08:00），[0,86400)，EMS 每小时一次共 24 次。动态检查60 s、观测年龄20 s、执行延迟10 s、PV阶梯1 kW/s，记录/显示仅后处理。沿用现有联合策略；单一执行器调用冻结物理积分。新日 PV AC 端口6 kW，原输入峰值5.8不变；电池10 kWh、±3 kW、效率0.95/0.95、SOC[0.2,1]不变；旧两小时5 kW不变。

数值容差：P=1e-9 kW，S=1e-9 SOC，T=1e-7 s，E=2e-9 kWh（片段/两小时窗），D=2.4e-8 kWh（日，且各两小时窗同时满足E）；X为精确相等。守恒使用实际交付，购售分别累计，软目标缺口不是耗能。90 s许可门、96 s现有审计与97 s限定完整PV响应包络分别记录；97不能豁免96失败。密集事件与末端未收束不计整体PASS。

## 先验矩阵（实施前冻结；执行状态另见末节）

| 项 | 输入 | 预期/容差 | 失败条件 |
| --- | --- | --- | --- |
| T1 | 原13×2场景、旧39专项、5 kW/7200 s | 原事件14/软缺口12；P/S/E/X | 改默认、弱化断言、删非零记录 |
| T2 | 原Demo/API/CLI | 旧类型/文件合同X，冻结文件无diff | 默认换引擎或旧输出改变 |
| T3 | UTC/+08等价；NaN、重复、倒序、缺点、时区歧义 | 等价X，非法执行前拒绝 | 补点、篡改输入、部分执行 |
| T4 | 原日输入；SOC0.5/1/0.2；ideal/dynamic | 24决策X，SOC S、功率P、守恒E/D | 越界、双状态、请求替实际 |
| T5 | 固定时刻，仅物理步3600/60/15 | 事件T、控制X、SOC S、能量E/D | 额外决策/漏事件或差异超限 |
| T6 | 首半小时购2 kW、后半小时售2 kW，电池不动 | ideal购售各1 kWh，E；dynamic单独核算 | 净0冒充购售均0 |
| T7 | 撤销4000恢复4100、同刻SOC/EMS、e40/41 | 原顺序X/T；孤立无PV撤销0.025 kWh，E | 旧请求复活、提前生效、删违规 |
| T8 | 原5.8配新6；5配5.8/6配6.01负例 | 参数X、90/96/97对象分开 | 改PCS、削输入、放宽审计 |
| T9 | 仅record/display变60/5、15/1、3600/60 | 原ledger/控制/能量X | 视图影响积分或漏峰 |
| T10 | 0/3600/86400及86390事件 | 末端无决策；未收束明确标注 | 25次决策、虚构停止 |
| T11 | 旧请求−1与联合+3的明确策略反例 | 不要求策略能量相同；同请求物理S/E/D | 实际代请求、强求闭环相等 |
| T12 | 1 kW×1 h、SOC到界含900 s空闲、非法时长 | 解析效率/能量/时间E/S/T | 重扣损耗、只裁SOC |
| T13 | ledger→小时/日报/曲线，删行重行负例 | 聚合E/D、SOC S、峰P、单位正确 | 平均后取正负、缺口当耗能 |
| T14 | 同输入独立目录、失败及已有目录 | 数据X，失败无完成，不覆盖 | 伪续算、半成品PASS |
| T15 | 爬坡/PV下降交错、密集及末端事件 | 实际记账，NOT_COVERED/INCOMPLETE | 未知当PASS、重置预算 |
| T16 | 相关、Campaign、full、static、独立复审 | 真实终态/exit/skip；范围无扩大 | 100%或报告代替终态 |

## 门禁与保全

先定向专项，失败先定位。若需修改冻结算法/预算或扩大路径，立即保留证据并报告，不继续放宽断言。通过后再相关回归、Campaign、全项目及静态门禁；独立复审注明是否实际运行测试。只在全部通过后本地提交、D盘持久恢复材料和新目录导入来源确认/日专项复测；不push、不发布、不改旧Demo。

## 实际结果

### 首次实施终态（历史）：BLOCKER，未通过整体验收

解释器：`C:\Users\22908\Desktop\eos-codex\.venv\Scripts\python.exe`，Python 3.12.14。工作树为 `C:\Users\22908\Desktop\eos-codex\sim-time-energy-baseline-worktree`，分支 `baseline/sim-time-energy`，HEAD 仍为上述基线。没有提交、push 或发布。

实际执行命令（在该工作树运行）：

```powershell
& 'C:\Users\22908\Desktop\eos-codex\.venv\Scripts\python.exe' -m pytest tests/unit/ems_simulator/test_pv_grid_charge_joint_probe.py tests/unit/ems_simulator/test_joint_daily_adapter.py tests/integration/test_joint_daily_demo.py tests/integration/test_ems_simulator_demo.py -q --basetemp 'D:\项目数据\EOS\runs\joint-daily-20261013-e970e099d29f489398e7813e85793bec\01-targeted\basetemp' -p no:cacheprovider --junitxml 'D:\项目数据\EOS\runs\joint-daily-20261013-e970e099d29f489398e7813e85793bec\01-targeted\junit.xml'
```

pytest 终态：**65 passed、9 failed、0 errors、0 skipped，74 total，exit 1，3.41 s**。stdout、stderr、JUnit、命令及起止时间 manifest、exit.txt 均保存在 `01-targeted`。该进程使用本轮 D 盘 TEMP/TMP 和 basetemp，未改全局配置。

| 测试组 | 本轮实际结果 |
| --- | --- |
| 原联合专项 | 39 passed |
| 原 Demo | 7 passed |
| 新日入口集成 | 4 passed |
| 新适配器 | 15 passed、9 failed |

旧 14 条动态事件、12 条软目标缺口及 5 kW/7200 s 默认值的显式检查通过。理想 60 s 默认日场景已生成 24 次决策、曲线及分项账本；独立目录重算、拒绝覆盖和模拟输出失败的 manifest 行为通过。这只支持这些已运行场景，不能升级为动态日入口验收。

九个失败全部止于既有 `tools/pv_curtailment_probe.py` 的 `unrepresentable slice changed SOC` 断言：ideal/dynamic 与三种初始 SOC 的六项步长对照、记录频率、撤销恢复、末端/密集事件三项。列表构建途中异常，不能推断每个步长都失败，也不能宣称其后控制次数、预算与能量断言已经执行。16 项矩阵尚未全部覆盖和通过；同刻组合、T12 解析/边界专项复用、T15 爬坡交错等仍须在阻塞解除后补足逐项证据。

### 最小诊断与冻结边界

`02-diagnostic`：ideal、3600 s 单独调用 exit 0，未复现；这不是整组步长对照通过。

`03-dynamic-diagnostic`：dynamic、60 s 单独调用 exit 1，捕获原异常帧，没有 monkeypatch、改变输入或修改算法。实际导入来源为本工作树。数值：

- 绝对时刻 `41136.896491228035 s`；该时刻 ULP 为 `7.275957614183426e-12 s`。
- 局部片段 `[0, 1.402386978473882e-12] s`，充电实际功率 `3 kW`。
- SOC 从 `0.9999999999999999` 变为 `1.0`，变化 `1.1102230246251565e-16`。
- 转绝对时间后，两端均为 `41136.896491228035 s`，可表示时长为零。

已确认直接机制是局部时间与绝对时间的浮点分辨率不一致。SOC 残差更早在哪一次换算产生仍待进一步定位。当前没有证据证明 96 s 响应审计失败，异常发生在其前；不得用 97 s 包络覆盖，也未改任何容差。

消除此问题可能需要改变旧探针的时间坐标/账本接续语义，超出本轮“只传时长和配置”的冻结要求，故停止。最小待批准评估范围为旧探针的时间适配、新适配器回归和本文；尚不能断定必须改 `ems_simulator/time_energy.py`。禁止删除保护断言、吞掉带 SOC 变化的切片、任意增大容差或只裁 SOC。

### 独立审阅和未执行项

独立审阅者 `daily_integration_blocker_review` 亲自读取源码、Git 差异、原始 stdout/JUnit/exit，**没有亲自运行测试**；结论 BLOCKER，确认旧探针差异为参数传递，故修复时间处理需另获授权。该结论不是整套代码的最终发布审阅。

本轮没有执行后续完整相关回归、Campaign A–F、full pytest、最终 Ruff/format/mypy/pre-commit；既有 158/62/2958 及旧恢复 39 仅为前置历史证据。没有本地提交、完整恢复验收、push、PR 或设备操作。当前源码为未验收草稿，不能直接用于替换旧 Demo。

本轮未提交文件、补丁和证据将单独保存于 D 盘唯一 blocked 快照；该快照不是通过验收的恢复包，也不包含新的 Git 提交。备份结果与校验以快照清单为准，不能用旧 3479325 恢复包冒充本轮成果。

## 首次最小时间坐标修复（历史）：80/7 未通过

### 实施范围和不变量

本次用户另行批准仅修复坐标/账本接续。相对上一版改动：

- `tools/pv_curtailment_probe.py`：保存 origin + local 两分量物理时间，合并同一次物理调用内无法表示为独立绝对区间的片段；保留每个原始片段。
- `tools/pv_grid_charge_joint_probe.py`：审计展开原始片段，使用局部持续时间；事件归属先确定正宽父行，再展开子片段。
- `tools/joint_daily_output.py`：任意窗口能量、峰值及 SOC 取原始片段；曲线标明区间平均功率，补充 `physical_parts.csv`。
- `tests/unit/ems_simulator/test_joint_daily_adapter.py`：近满/近空、大偏移、步长和事件首尾归属回归。
- 本文及接入评审文档：必要状态记录。

旧 `DailySimulationRunner`、`ems_simulator/time_energy.py`、物理公式、效率、SOC 硬边界、P/S/T/E/D/X 容差及 90/96/97 s 预算均未改变。其余已有日入口草稿保留；没有新建范围外生产文件。

先确定以下不变量，再作修复：同一次物理调用内的外部事实和执行请求不变；不跨 EMS、事实、执行效果或 ramp 边界合并；组的首末 SOC 来自原始片段；每个原始正时长片段均保留，不删除任何能量；购售分别累计；合并行只表示区间均值，不能替代峰值与持续时间；没有人为推进时刻或裁剪 SOC。

局部积分公式原本能够表示极短正时长，而平移后的双精度绝对端点不能。这是执行器表示层不兼容的证据，不能据此认定物理公式错误。本次将同一调用的首端残余并入后继、末端残余并入前驱，但原始 origin/local 及功率/SOC 全保留；审计记录的绝对标签即使重合，也须同时读取局部正时长，不能理解为零时长状态跳变。输出正宽父行是展示容器，不是一套新物理模型。

### 修复前后可核验记录

本轮根目录：`D:\项目数据\EOS\runs\joint-daily-time-repair-20261013-49fe916b80494e9882960d458292aaf7`。
Python 同上，pytest 实际版本 `8.4.2`。每组目录均有 stdout/stderr、JUnit、含准确 argv/时间的 manifest 和 exit.txt；所有测试临时目录在该组 D 盘目录内。

| 目录 | 实际测试 | 终态 |
| --- | --- | --- |
| `01-before-minimal` | 初始 SOC 距1.0/0.2各一ULP、空闲39600 s后充放电；仅选 `late_boundary_coordinate_regression` | 2 failed、24 deselected，exit 1；原时间断言 |
| `02-after-targeted` | 全部适配器+日入口集成 | 26 passed、4 failed，exit 1；时间断言已消除，理想馈网失败 |
| `03-final-targeted` | 加入偏移/步长/窗口归属和旧专项/旧Demo | 79 passed、8 failed，exit 1；含新增期望值乘除顺序一ULP问题 |
| `04-terminal-targeted` | 同上完整定向范围 | **80 passed、7 failed、0 errors、0 skipped，87 total，9.85 s，exit 1** |

最终命令范围（完整绝对 basetemp/JUnit 路径在 `04-terminal-targeted/manifest.json`）：

```powershell
& 'C:\Users\22908\Desktop\eos-codex\.venv\Scripts\python.exe' -m pytest tests/unit/ems_simulator/test_joint_daily_adapter.py tests/integration/test_joint_daily_demo.py tests/unit/ems_simulator/test_pv_grid_charge_joint_probe.py tests/integration/test_ems_simulator_demo.py -q --basetemp 'D:\项目数据\EOS\runs\joint-daily-time-repair-20261013-49fe916b80494e9882960d458292aaf7\04-terminal-targeted\basetemp' -p no:cacheprovider --junitxml 'D:\项目数据\EOS\runs\joint-daily-time-repair-20261013-49fe916b80494e9882960d458292aaf7\04-terminal-targeted\junit.xml'
```

| 最终组别 | PASS | FAIL |
| --- | ---: | ---: |
| 新适配器 | 34 | 3 |
| 新日入口集成 | 3 | 1 |
| 原联合专项 | 36 | 3 |
| 原 Demo | 7 | 0 |

近满/近空 × 39600/82800 s偏移 × 3600/60/15 s 共12项通过；事件首尾片段只归属一个窗口的独立消费者测试通过。该窗口测试为审计输入夹具，不是伪造物理模型 PASS。03 的一ULP期望问题以“先秒转小时，再乘功率”的一致单位运算顺序修正，整片段聚合先算无量纲比例；未增大任何容差或删除断言，原失败保留。

原14条动态事件与12条软目标缺口的默认场景检查通过，但不能据此说原39项全过：三项旧 ideal 步长回归 `full_pv_load_drop`、`upper_soc_same_time`、`same_time_facts` 现在失败。

### 当前实质阻断：SOC触界后的理想限发接续

default ideal 日场景的原始片段显示：

- origin `41040.0 s`，局部 `[25.263157894696196,25.263157894696633] s`；
- SOC 首末均 `1.0`，实际电池功率 `0 kW`，电网 `-3 kW`；
- 正时长 `4.369837824924616e-13 s`，售电 `3.641531520770513e-16 kWh`。

旧转换在绝对端点重合且 SOC 不变时会跳过该尾片段；当前按用户要求保存能量及峰值，不能继续跳过。冻结 ideal 规则要求无 excursion，因此即使动态预算 `within_budget=True`，仍必须判 FAIL。不能使用97 s包络、业务能量容差或平均功率把它变为理想 PASS。旧联合三项也暴露类似尾段，属于当前回归失败，不能只说新入口失败。

这是已观察到的执行器 SOC 触界与 PV 限发接续问题；还没有证明必须改物理积分模块。下一步应先审查如何在精确 SOC 事件处接续理想执行，不改变请求策略、能量、物理公式或零馈网判据。若需要改变理想执行语义或物理模块，应先报告并另获授权，不能自动扩大本次范围。

### 独立复审、停止和保全

实现由 Manager 当前任务完成；非实现者 `time_coordinate_review` 只读检查源码与本轮原始日志，**没有亲自运行测试**。其发现的跨窗重复归属已修复（父行严格归属后展开），实质 ideal 阻断仍成立。没有最终无阻断结论。

没有进入更广相关回归、Campaign、full pytest、最终静态/pre-commit 门禁；没有本地提交、新目录恢复复测、push、PR或发布。冻结路径差异检查不等同于完整静态门禁。

旧未验收快照 `joint-daily-blocked-3479325-20261013-dd1bc649ac65469b80acd88220234b10` 的42项SHA256重新核对一致，原件未覆盖。当前候选和01–04失败/通过记录另存D盘唯一 blocked 快照，以其manifest/SHA256清单为准。这只是现场保全，不是通过验收或可独立启动的完整恢复包。

## 接续最小修复（2026-10-13）

### 根因闭环与实际修复

原始 65/9 中 `41136.896491228035 s` 的局部 `1.402386978473882e-12 s` 小于该全天坐标的 ULP；局部切片能合法改变一 ULP SOC，但把两端分别加偏移会舍入成同一数。因此根因在执行器的时间表示，不是冻结积分公式错误。

保留 origin/local 切片后，进一步显露原转换曾跳过的理想模式极短馈网尾段。责任仍在接续：将局部 SOC 到界时长先做 `now + duration`、再用 `end - now` 还原，会改变传给物理层的时长；跨多次物理 SOC 舍入更新预测一个终点，也可能让实际到界早于执行器的接续点。

本次在 `tools/pv_curtailment_probe.py` 保留原局部到界时长直接传入 `PowerInterval`；每一个原有物理步结束即接回实际 SOC，下一步用这个已返回状态计算到界时间。返回物理状态不等于重新 EMS 决策，原 EMS、观测效果、ramp 和 ideal SOC retarget 条件均不变。动态延迟不会因此变成瞬时理想控制。没有修改 `ems_simulator/time_energy.py`，也未修改旧运行器、物理公式、效率、SOC 硬界、策略或容差/预算。

所有物理切片仍保存 origin/local 时间、实际功率、SOC，正宽父行仅为展示容器；不删除极短片段、不跨事实/控制事件合并、不推进无能量核算的时间。事件先按父行取得唯一归属，再展开子片段计峰值、时长和能量，避免同一舍入端点被两侧重复计入。

### 继续运行的真实记录

证据根：`D:\项目数据\EOS\runs\joint-daily-step-return-20261013-8e24e1fcd8214fedb852093700ebdff7`。每个测试目录保存实际 argv、起止时间、stdout/stderr、JUnit、manifest 与 exit。Python 路径和 pytest 版本沿用上文。未并行启动 pytest。

| 目录/尝试 | 真实终态 | 说明 |
| --- | --- | --- |
| `joint-daily-coordinate-continuation-20261013-09948b3129f244a6a620297281c44a38`（同级目录） | 83 passed、4 failed，exit 1 | 只去掉局部时长往返转换仍不够；失败保留 |
| 根目录 | 87 passed，12.44 s，exit 0 | 加入逐物理步接续后，新适配器/集成/旧39/旧Demo7通过 |
| `related` | 158 passed，4.28 s，exit 0 | time_energy、旁路、闭环、约束、网充联锁、限发、联合七组 |
| `campaign` | 62 passed，389.86 s，exit 0 | 原有 A–F 六文件；本次运行的真实终态，不沿用旧证据 |
| `contract-focused` | 无测试收集，exit 4 | 命令误写不存在的旧Demo路径；原日志保留，不算测试失败或PASS |
| `contract-focused-correct-path` | 100 passed，13.68 s，exit 0 | 修正为实际 `tests/integration/test_ems_simulator_demo.py`；新增合同用例通过 |
| `full` | 3012 passed，435.86 s，exit 0 | 本次真实全量，收集于追加34项复审测试之前；不是最终测试集合数量 |
| `review-coverage` | 134 passed，17.92 s，exit 0 | 追加精确合同用例及按物理单位收紧的断言 |
| `static` | Ruff exit 1（9项）、format exit 0、scoped mypy exit 1（1项）、repo mypy exit 1（2项） | 原始失败保留；导入、名称遮蔽、长字符串、等价pairwise、XML属性类型与测试时区抽象方法修正，不改物理或约束 |
| `static-final` | Ruff/format/scoped mypy/repo mypy 均 exit 0 | 856格式文件、5/364 mypy source files；冻结diff exit 0，有限敏感及生成物扫描0匹配 |
| `post-static-focused` | 134 passed，17.53 s，exit 0 | 静态修正后同一专项范围再次验收 |
| `precommit` | 整体exit 1；前三hook Passed；pytest 3046 passed、0失败/错误/跳过，463.477 s（JUnit） | Manager在pytest hook期间更新两份文档，触发files modified保护；不是pytest断言失败，不是pre-commit通过。七个代码/测试文件SHA与static-final记录一致 |
| `precommit-final` | 四hook Passed，整体exit 0；pytest 3046 passed、0失败/错误/跳过，439.929 s（JUnit） | 2026-10-13 16:50:55.527–16:58:33.726 +08:00；九文件运行前后SHA完全一致。仅此记录作为最终pre-commit PASS |

新增合同用例包括：e40/e41 观测相位（分别 0/0.05 kWh 响应期网充）；同刻 SOC/事实/许可及交错队列场景延伸到24h；6 kW cap 在136 s、实际PV在137 s完成上升；96.5 s 审计负例不能借97 s包络转PASS；132 s输出爬升中于133 s失去PV，实际回到0、负载仍由电网供给，并明确 NOT_COVERED。原14条动态事件、12条保电软目标缺口显式检查仍通过。

非实现者 `coordinate_continuation_review` 已给代码/覆盖 **KEEP**，但最终交付门禁仍 PENDING；其亲自读取源码、断言、stdout/JUnit/exit和静态证据，**未亲自运行测试**。原始34项补充暴露的是合同覆盖缺口，不是物理算法新缺陷；补充与收紧断言通过后，未发现需要扩大算法范围的阻断。

### 16项合同的实际证据映射

| 合同 | 最终测试中的支持（完整节点可由JUnit检索） | 边界 |
| --- | --- | --- |
| T1 | `original_defaults_and_evidence_counts` + 原39专项 | 14动态/12软缺口保留；不保证任意场景 |
| T2 | 原Demo7项含main CLI调用、重复数据比较；`legacy_demo_keeps_its_files`；冻结diff | 旧路径未替换；不把新曲线当旧CSV |
| T3 | `timezones_are_equivalent_not_civil_day_shift`、`nonfixed_timezone_and_naive_source_rejected`、事件/PV/重复倒序/坏事实负例；相关/全量中的旧immutable input测试 | 部分非法数据先被旧输入构造器拒绝，不冒称全部由新适配器负责；不支持可变时区日 |
| T4/T5 | `daily_baseline_three_physical_steps`、`switching_daily_step_and_view_invariance` | D0/上下界及切换；P/S/E/D按物理量分开；不改变控制周期配平 |
| T6 | `reverse_flows_do_not_net_out`、`dynamic_reverse_flow_uses_actual_ramp_not_ideal_totals` | 动态按实际爬坡独立核算，不能套理想各1kWh |
| T7 | 撤销恢复、e40/e41、四类同刻/交错场景延长24h | 原场景延长被明确标记，不称原测试本身改变 |
| T8 | 原曲线/固定参数、旧5kW拒5.8、新6kW拒6.01、完整响应及96.5审计负例 | 97s不能豁免96s；全部为仿真假设 |
| T9 | D0与T7的显示/记录变化精确不变性 | 视图不触发控制，不从采样点积分 |
| T10 | `final_event_keeps_uncleared_nonzero_violation`、非法终点事件 | 保留6kW×10s，stop=None、非PASS、恰24次EMS |
| T11 | 旧−1/联合+3策略反例；本次相关旁路回归 | 不要求不同请求下相同能量 |
| T12 | `contract_exact_one_kwh_efficiency`、`contract_idle_boundary_perturbations`、`contract_illegal_physical_duration` | 精确10kWh/.95；±1kW一小时，900s空闲后上下界，±1e-6s、三步长及非法时长；不修改冻结公式 |
| T13 | 分窗能量/唯一归属、坏账本负例、`hourly_csv_reaggregates_the_unique_ledger` | 原始局部片段权威，展示行平均值不代替短峰 |
| T14 | 两个目录重算一致、已有目录拒绝、故障manifest | 无暂停续算；新目录恢复门禁另列 |
| T15 | `pv_loss_really_intersects_output_rise`、密集/末端非PASS | 保留NOT_COVERED/INCOMPLETE，非任意切换保证 |
| T16 | 本节所有实际终态及独立复审 | pre-commit、提交/恢复以最终回执为准，不预填 |

当前D盘小型检查点：`D:\项目数据\EOS\backups\joint-daily-candidate-checkpoint-196bb3564d594affa97a0c11632a731f`，九文件和补丁共10项哈希核验。首次补丁导出因PowerShell原生命令参数表达式失败，已保留复制文件、重新核对后用字面量参数补齐；不影响代码/测试。它不是完整恢复包，不覆盖旧失败快照。

### 最终日输出（文件冻结重取pre-commit之前）

同一证据根下 `demo-ideal` / `demo-dynamic` 为真正CLI调用生成，不是手写PASS报告。命令与退出码在 `demo-commands`，两次均exit 0；各输出含`ledger.csv`、`physical_parts.csv`、`joint_hourly.csv`、记录/显示视图、`joint_power.svg`、SOC曲线与`joint_summary.json`。两次恰24次EMS，末SOC 0.2。

| 指标（kWh，另注除外） | ideal | dynamic |
| --- | ---: | ---: |
| PV可用 | 39.6 | 39.6 |
| PV实际交付 | 19.021052631579 | 19.061305555556 |
| 弃光 | 20.578947368421 | 20.538694444444 |
| 负载 | 29.4 | 29.4 |
| 充电/放电（AC端分别累计） | 8.421052631579 / 10.45 | 8.421052631579 / 10.45 |
| 购电 | 8.35 | 8.358361111111 |
| 售电 | 1.8503717077085942e-18 | 0.048614035088 |
| 转换损耗 | 0.971052631579 | 0.971052631579 |
| 网充违规 | 0 | 0 |
| 馈网峰值（kW） | 1.1102230246251565e-16 | 3 |

ideal浮点残量未抹零，低于既定数值判据；dynamic的5条馈网记录实际保留，不声称严格瞬时零馈网。此默认日没有网充请求和保电软缺口，不替代专项中的响应期违规网充与原场景12条软缺口证据。

### 启动与最终交付边界

从源码工作树运行，每次使用不存在的D盘输出目录：

```powershell
Set-Location 'C:\Users\22908\Desktop\eos-codex\sim-time-energy-baseline-worktree'
$dailyRun = Join-Path 'D:\项目数据\EOS\runs' ('joint-daily-manual-' + [guid]::NewGuid().ToString('N'))
& 'C:\Users\22908\Desktop\eos-codex\.venv\Scripts\python.exe' -m tools.joint_daily_demo --mode ideal --output (Join-Path $dailyRun 'ideal') --step 60
& 'C:\Users\22908\Desktop\eos-codex\.venv\Scripts\python.exe' -m tools.joint_daily_demo --mode dynamic --output (Join-Path $dailyRun 'dynamic') --step 60
```

本次只是规定有限场景的独立UTC日仿真验收。没有替换DailySimulationRunner，没有设备/协议/网络能力，没有暂停续算。记录/显示频率不参与物理积分；6kW端口及全部延迟均是显式仿真假设。密集事件与末端未收束继续非PASS。

实现和门禁由Manager执行；非实现者只读复审，未亲跑测试。最终pre-commit之后只更新两份文档的事实状态，不再改七个Python文件；文档格式、精确范围及diff需在提交前再次检查。已获准的下一动作仅为本地提交及D盘新目录恢复；其是否成功，必须看恢复包中的HEAD、SHA256、import来源、JUnit和退出码，不能由本文预先宣称。未push、未发布、未连接真实设备。
