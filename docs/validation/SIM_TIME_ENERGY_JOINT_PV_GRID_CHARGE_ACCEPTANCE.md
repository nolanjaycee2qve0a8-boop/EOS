# PV 限发与网充许可联锁：联合仿真验收合同

基线为 `6243a0bd0bc7979a60cea7c51843f97ac11f6518`，前置网充联锁为 `0c63698ae9bb40b6ce994c44f296d11f187dba79`。场景和数值阈值在联合测试之前写定；独立复审指出最初将新增“零延迟许可硬线”误当成前置动态网充联锁的缺口后，在最终验收前修订为共享原联锁约束函数及其 60/20/10 秒时序。初始草案和失败开发记录不得当成最终 PASS。入口只调用一次既有 PV 执行器和一次连续物理状态/账本；不将两个仿真的结果拼接，不替换 `DailySimulationRunner`。单 AC 母线：电池正号为充电，电网正号为购电；`grid=load+actual_battery-delivered_PV`。PV 可用、交付、弃光分别积分，冻结的物理层只按实际交付 PV 与实际电池功率计算 SOC、损耗和购售电。

## 五类时刻与同刻顺序

1. 外部 PV/负载、许可、Zero Export、保电目标事实在指定时刻右连续生效。SOC/功率硬限始终生效；网充许可与 Zero Export 的快速执行受同一观测/检查/执行时序约束，不额外假设零延迟硬线。
2. EMS 仅在 `0,3600` 秒读 SOC/事实并形成新请求；事件、记录或执行检查不增开 EMS 决策。
3. 动态执行层每 60 秒检查，读取 20 秒前的 PV/负载/模式/许可事实，10 秒后使检查结果生效。启动后不足完整 20 秒的检查不得通过把负时间夹为 `t=0` 来提前获知事实；默认首次有效检查在 60 秒、首次效果在 70 秒。理想极限采用零延迟，并在事实事件时额外检查。初始观测尚未成熟时，PV 与电池执行均 fail-closed 为零。
4. 同刻依次处理右连续事实、已到期的执行效果、计划中的 EMS 决策、旧请求锁存、执行目标、下一半开物理区间。PV AC 端口上限 5 kW，动态 cap 与输出上升各按 1 kW/s；实际 PV 突降可立即降低输出。物理步在事实、检查效果、爬坡及 SOC 边界切段。撤销许可到有效限制之间可能真实网充；到期后恢复许可不能使旧正向请求自动复活，需新 EMS 决策。
5. 记录/显示仅观察物理账本，不触发控制或重复累计。

## 约束优先级与不可满足项

SOC 硬上下限、±3 kW 电池及 5 kW PV 端口限制由物理/执行层强制。网充许可撤销后，按已声明延迟停止电网给电池充电；停止前的违规功率/时长/电量必须如实记账，停止后的充电不得超过当前**实际交付 PV**减负载后的正向余量；普通购电供负载允许。有效撤销锁存旧充电请求，到新 EMS 决策前即使许可恢复也不能重放。Zero Export 理想模式协调 PV 与电池共同不馈网；动态模式允许规定延迟内短时馈网，但必须如实记售电。保电目标是软目标，不允许越过前述硬约束，目标差距/未满足量需列出。PV 不能被电池或负载接纳时限发并计弃光；无法在动态延迟内同时满足 Zero Export 时记录馈网峰值、时长、电量，不能改写负载或夹零电网功率。

两项执行规则使用同一 SOC、同一物理切段、同一逐段能量账，不把 ACK、请求或测量时刻当作物理完成。原网充入口与 PV 执行器共用 `constrain_charge_request` 纯约束函数；联合入口提供场景与审计，不复制积分器或另写优化器。原 PV 专项入口另有即时 actual-PV-surplus 二次门；联合入口显式关闭该**全时**额外门，才能按旧联锁的延迟观测语义如实报告许可已 off 后 PV 突降的 2000–2050 秒短时网充。但当本执行器自己的 PV AC cap/output 正在上升时，仅能按已实际交付的 PV 余量允许正向电池请求；否则已知的自身爬坡会把尚未发出的 PV 误当作已交付，甚至在 off 效果生效后重新启动网充。这个受控爬坡保护不把后续外部 PV 突降变成瞬时可知事件。它仍是新联合仿真，不可把原网充入口的 RevocationOutcome 当作联合入口实际报告。

边界：若**外部 PV 突降恰与受控 AC 输出上升交错**，上升保护可能比原延迟联锁更早收紧；本轮有限场景不覆盖这种交错，不能宣称所有 PV-loss 事件都与旧入口具有完全相同的停止时刻，更不能推及真实设备。

## 预设预算与数值容差

联合动态路径从同一事实事件到两项约束都稳定的保守上界为 `20+60+10+5/1=95 s`。许可的**观察/执行门**单独最多 90 秒；若撤销许可和 PV 从零突增重合，观测到的可用 PV 先于 AC 端口实际交付，网充停止还可能等待最多 5 秒爬坡，因此联合网充响应也按 95 秒，而非只按前置的 90 秒。两者并行作用于同一执行器和账本，不能把某次实测 70 秒或单独 90 秒冒充联合最坏上界。最坏同时 PV 5 kW 与电池放电 3 kW，馈网峰值上界 8 kW、单 excursion 电量上界 `8×95/3600=0.211111111 kWh`。违规网充峰值上界 3 kW、单 excursion 时长 95 秒、电量上界 `3×95/3600=0.079166667 kWh`；稳定后的残余功率/电量数值限分别为 `1e-9 kW`、`2e-9 kWh`。普通负载购电不计违规。理想模式馈网及违规网充均要求零峰值、零时长、零电量（上述数值容差内）。动态任一 excursion 超出预算即 FAIL，不得事后放宽。观测前已发生的瞬态仍在单一账本中记录。

功率平衡容差 `1e-9 kW`，能量/跨步总量 `2e-9 kWh`，SOC `1e-9`，时间 `1e-7 s`。物理步为 3600/60/15 秒，固定全部事实、EMS 与执行时刻；只改记录周期应使决策及能量完全一致。数值均为显式仿真假设，绝非 PCS/BMS、逆变器或现场承诺。

## 运行前场景清单与预期

| 场景 | 关键事实与预期 |
| --- | --- |
| 满电 PV 跳变、负载突降 | SOC 1；PV 0→5、后负载 1→0。理想限发且不馈网；动态可能先馈网，分别记交付、弃光及两次响应。 |
| 撤销许可后 PV 突降 | 旧正向 EMS 请求仍在；许可 off 后 PV 3→0。按旧联锁观测延迟预计 2000–2050 秒产生 `2×50/3600=0.027777778 kWh` 短时违规网充，2050 秒后残余为零；负载购电允许，未达软保电目标须报告。 |
| 撤销许可时 PV 突增 | PV 0→5 与 off 同刻，可用 PV 的延迟观察先于实际 AC 输出爬坡；必须计入许可门的延迟和额外 PV 爬坡导致的短时网充，按联合 95 秒上界判断，不把 90 秒单模块值硬套。 |
| 已禁止许可的启动 PV | 从 t=0 起许可 off、可用 PV 5 kW、初始输出 0：首次 70 秒效果后仍不得拿未爬升的 AC 交付量允许电池网充；无违规时报告“无观测违规”，实际停止时刻保持未知，而不是假报 t=0 停止。 |
| 放电时负载突降 | PV 与电池两路可能合计馈网；理想同时约束，动态如实计短时售电，不能只限 PV。 |
| 撤销、恢复与模式切换 | 许可 off/on 与 Zero Export on/off 交错；旧正向请求不自动复活，只有新 EMS tick 可以重新请求。 |
| SOC 上界同刻 | 电池恰好触顶于 3600 s EMS/外部事实时刻；不能多计充电、不能漏/重同刻事件。 |
| SOC 下界同刻 | 电池恰好触底于 3600 s EMS/外部事实时刻；不能再放电或用请求冒充实际交付。 |
| 延迟检查交错 | 许可在 1800/1810/1820/1900 s 变化；旧采样/执行效果按时间顺序成熟，不能在新的 off 效果成熟后复活旧充电请求；早于效果的违规网充按预算计量。 |
| 正在充电时撤销 | 4000 s 从 on 切至 off，4100 s 恢复；计量撤销到实际停止的迟滞和网充电量，恢复不能重放旧正向请求。 |
| 旧满电重放 | 负载 1 kW、PV 5 kW、SOC 1、持续 7200 s：旧无控制馈网 8 kWh；联合理想交付 PV 2 kWh、弃光 8 kWh、售电 0；动态记录启动迟滞、交付/弃光/购售电和残差。 |
| 限发解除与阈值抖动 | PV/负载在小阈值附近变化；只按预设检查/效果更新，不凭记录或每次事件新增动态决策，不出现无依据的请求符号跳变。 |
| 同刻多事实 | PV、负载、许可、模式、软目标同刻改变，处理一次事实边界与一条唯一物理账本。 |

每个场景输出逐段 CSV、状态/请求/实际功率曲线和未满足约束清单。旧 `4 kW×7200 s=8 kWh` 满电馈网与旧 `1.5 kWh` 网充违规保持为前置无控制失败事实，不倒写成当时已通过。发现现有接口无法证明某一同刻 SOC 条件时，标为未覆盖/不可满足，不改变源事实伪造通过。

## 门禁

先专项和既有相关回归，再 Campaign A–F、全量 pytest、Ruff/格式/mypy、独立只读复审；保留所有失败、跳过与重跑。通过后才可本地提交、制持久恢复包及新目录恢复复测。未授权 push、PR、硬件、协议或旧 Demo 替换。

## 本地联合验收记录（2026-10-13）

最终代码在基线 `6243a0bd0bc7979a60cea7c51843f97ac11f6518` 上运行，测试使用 Python 3.12.14、pytest 8.4.2。D 盘隔离运行目录为 `D:\项目数据\EOS\runs\joint-validation-20261013-366f07581877418e85311c618bf3cda6`；各次命令、stdout、stderr、退出码和 manifest 保留在该目录或此前的 `evidence-pv-grid-charge-joint-20261012`。没有真实设备、网络协议或旧 `DailySimulationRunner` 接入。

| 门禁 | 实际命令或范围 | 终态 |
| --- | --- | --- |
| 联合专项 | `python -m pytest tests/unit/ems_simulator/test_pv_grid_charge_joint_probe.py -q --basetemp <D盘新目录> -p no:cacheprovider` | 39 passed，exit 0 |
| 相关回归 | 同一 pytest 命令形式，覆盖 `test_time_energy.py`、`test_legacy_time_energy_sidecar.py`、`test_closed_loop_time_energy_probe.py`、`test_dynamic_constraint_probe.py`、`test_grid_charge_interlock_probe.py`、`test_pv_curtailment_probe.py` 和联合测试 | 158 passed，exit 0 |
| Campaign A–F | 六个 `test_residential_campaign_[a-f].py` 的独立聚合运行，独立 basetemp 与进程级临时目录 | 62 passed，exit 0 |
| 全项目 | `python -m pytest -q --basetemp <D盘新目录> -p no:cacheprovider` | 2958 passed，exit 0，454.06 s；终态未报告 skip |
| 静态 | `ruff check .`、`ruff format --check .`、`mypy --explicit-package-bases` 检查三份相关工具源码、`git diff --check` | 各 exit 0；格式检查报告 849 files already formatted；mypy 报告 3 source files 无问题 |
| 仓库级类型门禁（首次补充检查） | `mypy kernel capability objective simulator tests` | **FAIL，exit 1**：`tests/unit/ems_simulator/test_time_energy.py:26` 的既有 `evaluate` 函数缺少返回类型注解；检查了 362 份源码，只有这一项错误。首次检查时该文件尚未改动，基线 HEAD 中也存在相同定义；此失败不计为通过。|

失败与重跑没有被覆盖：首次 Campaign A–F 为 60 passed、2 failed、exit 1；两项都在旧 Campaign E 的 Windows 临时目录创建/清理处遇到 `WinError 5`，不是联合控制断言失败。随后 Campaign E 单独重取 5 passed、exit 0；完整 A–F 使用可写的本轮临时目录重取后 62 passed。C 盘上的前两次全项目运行虽显示进度 100%，均在最终 summary 前以 exit 120 退出，并有 Python `OSError` 退出堆栈；它们不计 PASS。D 盘新目录的全项目运行才取得上述 2958 passed、exit 0。未跳过或弱化失败用例，未修改全局 TEMP/TMP 或 ACL。

仓库 `.pre-commit-config.yaml` 的 mypy hook 使用上述广域检查范围，因此最初虽有 scoped mypy 通过，仍因仓库级类型门禁失败而停止提交。上述失败保留为历史证据。

用户要求继续 EOS 后，仅在既有 `test_time_energy.py` 导入 `TimeEnergyResult` 并为 `evaluate` 补充该返回类型，未改函数体或算法。新证据目录为 `D:\项目数据\EOS\runs\joint-closeout-20261013-713b6f312d564cf1a76c8d9a545dfba3`：Ruff、格式、仓库级 mypy（362 source files）、scoped mypy（3 source files）均 exit 0；时间模块与联合专项共 58 passed、exit 0，JUnit 无跳过。每项 manifest 记录完整解释器、argv、工作目录与进程级临时目录。

最终运行 `C:\Users\22908\Desktop\eos-codex\.venv\Scripts\python.exe -m pre_commit run --all-files --show-diff-on-failure`，进程级 `PYTEST_ADDOPTS` 使用上述 D 盘目录的全新 `precommit-basetemp`、禁用缓存并写入 `precommit-junit.xml`。四个 hook 全部 Passed，进程 exit 0，stderr 为空；JUnit 为 2958 tests、0 failures、0 errors、0 skipped，pytest 用时 467.350 秒。这是类型注解修复后的全项目实际运行。结束后 Git 恰为六个预期暂存文件，无 hook 引入的额外改动。随后仅补写本文终态记录；本地提交 SHA 和恢复复测结果由恢复包的 `COMMIT.txt`、`restore-manifest.json` 记录，不能预先声称恢复成功。

13 个预设场景分别以 ideal 与 dynamic 模式、60 秒物理步长输出，共 26 组，全部进程 exit 0。每组留有 `ledger.csv`、`curves.svg`、`request-actual.svg`、`excursions.csv`、`event-outcomes.csv` 和 `constraint-findings.csv`；SVG 已解析核对，汇总见 D 盘 `scenario-summary.csv`。另由联合测试对同一场景覆盖 3600/60/15 秒物理步长及记录频率不变性。旧满电案例在理想联合模型下交付 PV 2 kWh、弃光 8 kWh、售电 0；动态 `revoke_pv_loss` 如实记录 2000–2050 秒违规网充 `0.027777778 kWh`，动态负载突降场景也保留非零售电，均未事后夹零。

26 组场景共保留 14 条动态 excursion，全部在运行前声明的预算内；另有 12 条 `SOFT_TARGET` 保电目标未达记录。后者没有被删除或改写为“目标已达到”，联合通过不代表所有软目标瞬时实现。

独立复审结论为 KEEP；复审者只读审查合同、代码、备份哈希及原始日志，没有亲自运行 pytest。复审中出现过仓库级 mypy BLOCKER，类型注解修复后重新核验并解除；各轮记录保存在项目外证据目录。上述本地测试由 Manager 运行，独立复审不能替代其终态证据。本轮验收只证明规定仿真假设与有限场景下的行为，不承诺真实设备瞬时零馈网或现场安全性能。
