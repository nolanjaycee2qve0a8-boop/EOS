# 同输入、同执行器策略对照：先验合同

## 首轮历史终态：BLOCKER，未验收、未提交

2026-10-14：HEAD仍342849c；以下结果为本轮实际输出，先验合同及阈值不变。

证据根：D:\项目数据\EOS\runs\strategy-comparison-20261014-f2cba3cdebce49acb45691dcee0016e7。

- 改造前完整基线：9组捕获，exit0，baseline/*.json.gz及hashes.json。
- 01-targeted：python -m pytest tests/unit/ems_simulator/test_joint_strategy_adapter.py tests/integration/test_joint_strategy_comparison.py -q --basetemp <独立D盘目录> -p no:cacheprovider --junitxml <同目录/junit.xml>，31 passed、4 failed，13.13s，exit1，无跳过/错误（JUnit为准）。失败均为基础策略original/reserve × ideal/dynamic的result.passed断言；后续步长/指标断言在失败处未完整执行，不能计为已通过。
- 02-compatibility：外部verify_strategy_compatibility.py读取9组改造前结果，分别比较改造后省略参数与显式原策略。完整JointResult逐字段18/18精确相等，exit0；没有放宽容差。
- 03-failure-diagnosis：仅重放original basic ideal/dynamic的60秒步長两组并保存全账本。命令exit0仅说明诊断捕获成功，两个场景仍passed=false。
- 未执行后续原日/联合/旧Demo/相关、Campaign、全项目、最终静态门禁，也未提交或恢复复测。

根因已通过源码和原始片段对照定位：pv_curtailment_probe执行器的charge_absorption直接使用battery_target计算PV限发目标，隐含上游已按PCS功率封顶。基础策略保留原始PV−load请求，10:00可为4.1 kW，物理层实际充电仍限3 kW，PV5 kW与负载0.9 kW留下1.1 kW馈网。这不是丢失能量或物理公式变化，而是请求与可执行吸收能力混用。ideal原日累计馈网1.8372807017544122 kWh、约5100s、峰4.7 kW；dynamic累计1.858141812865496 kWh，其中长事件36000–41175s、5175s、1.8427251461988294 kWh，超原96s审计。

停止原因：正确处置需在执行协调层明确PCS可执行充电能力后决定PV限发，属于安全执行行为变化，超出本轮“仅策略接口”授权。未在适配器裁剪基础请求，未修改物理/事件/延迟/预算，未将低弃光或相同购电成本误判成策略收益。经济函数部分测试通过不等于完整对照已验收。独立只读复核及增量保全回执在外部证据目录，未亲自测试的审查不得写成测试通过。

基线：342849c96f9e50b12c730e9c17b5a16ab4dc5d18。2026-10-14 用户批准三文件接口扩展。本文件先于实现与结果写定；当前尚未验收，不表示已运行或通过。

## 追加授权：仅执行层PCS能力协调修复

新证据根：D:\项目数据\EOS\runs\strategy-capability-repair-20261014-93631cb475b0460583823c3515d6d620。旧失败包不覆盖。修复前新增最小test_pcs_overrequest_minimal已失败：原请求4.1、实际3、约束后仍4.1、PV5/负载0.9/电网−1.1；1 failed、exit1。

直接行为修复仅tools/pv_curtailment_probe.py。执行层在原延迟许可门之后，以±PCS上限形成battery_target，再按既有Zero Export规则协调PV；同一PCS限值用于既有SOC到界时长公式。原始请求不变，不是改策略。正充时边界时长=(1−SOC)×容量×3600/(AC功率×充电效率)，负放时=(SOC−下限)×容量×放电效率×3600/AC放电功率；这是原边界计算，仅修正分母不再使用超能力请求，不新增外部预测。

时间口径：原策略请求在EMS时刻产生；许可/Zero Export仍按原成熟观测生效，battery_target为当时已生效的PCS受限命令，constrained_request_kw还可受原PV爬坡许可保护降低。当前物理可执行能力另受即时SOC硬边界限制，满电/空电相应实际功率为0，不能用命令值证明实际交付；原理想SOC触界重算保留，动态SOC触界不触发提前观测或瞬时PV关闭，只等既有检查/执行/爬坡。原soc<1−1e−12协调防抖条件不变（SOC无量纲），物理SOC不裁剪、不增加容差。

不变量：物理模块、效率、硬界、事件序列、EMS24次、60/20/10s及1kW/s参数、90/96/97各预算不变。没有用剩余SOC能量除整段时长冒充此刻能力；物理在边界前后分段，保留所有能量和动态馈网。预计原策略请求已≤3，原9份基线18次比较仍应精确一致；若不同，先记录解释，不能更新golden掩盖。

## 精确范围

修改 tools/joint_execution_contract.py（策略标识校验）、tools/pv_grid_charge_joint_probe.py（策略透传）、tools/pv_curtailment_probe.py（既有 EMS 时刻调用可选策略，以及追加授权的执行层PCS能力封顶/PV协调和边界时长功率口径修复）。新增 tools/joint_strategy_adapter.py、tools/joint_strategy_comparison.py、tests/unit/ems_simulator/test_joint_strategy_adapter.py、tests/integration/test_joint_strategy_comparison.py 和本文件。共八文件。

不改 DailySimulationRunner、旧日入口与输出、任何物理积分/效率/SOC硬边界、事件顺序、延迟、预算和容差。保留既有执行联锁及限发机制，只加入上文明确获批的PCS能力协调修复。无全局 monkeypatch，无第二套执行器。

## 策略与只读接口

joint_reserve_v1 委托既有 dynamic_constraint_probe._request；demo_self_consumption_v1 委托既有 closed_loop_time_energy_probe._request（旧 Demo 请求规则的既有独立镜像），不复制规则。两者读取同种当前事实与各自轨迹 SOC，不读取对方状态或未来输入；前者在无 PV 富余、低于保电目标且允许网充时请求补电，后者无此分支。前者请求内已有功率封顶，后者原请求可能超过 PCS，仍由同一执行层约束。请求正充负放，电网正购负售。

只读输入为 frozen scalar snapshot：时刻、当前事实区间、PV、负载、许可、Zero Export、软目标、SOC及不可变电池参数副本；没有账本/执行器引用。策略只返回有限 int/float（拒绝 bool/NaN/Inf/其他类型），异常向上抛出。未知标识或 context 与实际策略不符执行前拒绝。不声称 Python callback 是敌意代码沙箱。

None 默认保留原请求调用；显式 joint_reserve_v1 必须精确等同基线。调用方自定义 callback 仅用于接口测试，正式对照用固定两种已有适配器。

## 公平条件与场景

UTC 2026-01-01 00:00 至次日00:00，北京时间08:00至次日08:00。区间[0,86400)，EMS仅0,3600,...,82800，共24次。终点不决策；小时内事实事件只影响既有执行机制，不新增 EMS。观测/检查/执行仍为60秒检查、20秒观测年龄、10秒执行延迟、1 kW/s PV阶梯；许可门90秒、既有审计96秒、限定完整包络97秒分别判断，97不豁免96失败。

原24点PV/负载不变，PV峰5.8、端口6 kW；电池10 kWh、PCS±3 kW、效率0.95/0.95、硬SOC[0.2,1]，初始0.5。ideal/dynamic分别运行，物理步3600/60/15仅改变切段。两策略每组接收完全相同Case与settings。

预先定义两个比较场景：original（原日许可false、目标0.2）；reserve（原PV/负载不变，t=0许可true目标0.8，t=5400许可false，t=7200许可true，t=21600许可false，t=64800目标0.9且许可true）。后者旨在暴露网充补保电规则和终库存差异，不是替换原输入。每个场景内两策略同输入；不能跨场景选赢家。

## 数值及兼容门禁

沿用P=1e-9 kW、S=1e-9 SOC、T=1e-7 s、E=2e-9 kWh、日D=2.4e-8 kWh；标识/决策次数/时刻/同实现确定性结果X精确相等。费用误差为日能量D乘本场景最高电价（CNY）；不放宽冻结物理容差。

改造前捕获原日ideal/dynamic×三个步长，以及reserve dynamic×三个步长的完整JointResult（Case、settings、decisions、ledger含本地物理片段、checks、views、excursions、event_outcomes、findings、passed）。改造后省略策略、显式原策略分别逐字段精确对比，不比较文件路径/运行编号/墙钟等外部元数据。捕获文件只作本次外部证据，不能被测试重写。

专项覆盖：只读快照、非法返回/异常/未知策略、策略与context不符、24次及自身反馈、默认三方精确兼容、两种策略步长一致、仅记录频率变化、库存差异、同策略零差异、区间双向潮流、跨电价边界、守恒与SOC/功率约束、许可/Zero Export实际动态判定。事件结果失败不得被软件测试通过掩盖。

## 唯一账本与指标

复用 validate_ledger/window_totals/physical_audit_rows；不从显示采样重积分。购售电分别累计、PV可用/交付/弃光、电池AC端充放电、转换损耗、初末库存、末端及过程软目标缺口（kWh及kWh·h）、馈网峰值/累计持续时间/电量、禁止网充量、每个原始excursion及预算结论单列。软目标不是硬界，也不是额外能耗。只报告本次事件/缺口计数。

## 经济口径

只使用 ems_simulator.demo 的示例购电价0.30/0.55/0.90 CNY/kWh及原UTC小时分配，非真实电价；不进入控制策略。现阶段未确认适用于此入口的售电价，故经济结果先交购电成本、售电能量及待定净费用公式 C=购电成本−p_export×售电量，不伪称完整净费用。期末价值复用 optimization.terminal_energy_value：硬下限以上库存×0.95×估值电价；敏感性采用已存在示例购电价0.30/0.55/0.90，列各策略净费用公式−期末价值及差额，不当成实际利润。输入完全相同则共同初库存价值在差额中抵消。退化、需量费、税费、固定费等未计，不重复扣转换损耗。若后续核实既有明确售电价，可引用出处后补记，不能自造。

物理片段按电价边界切账，保留origin+local时长，不能把小时平均净电量当作购售电；期末SOC不一致不能直接比较购电成本选赢家。

## 执行顺序与保全

实施期、结果运行前补充核查：ems_simulator/runner.py 的 TariffSimulationInput 第三参数明确为0.0，故本次售电价采用既有示例的0 CNY/kWh。净费用数值等于购电成本，仍单列售电量及零售电收入；不等于现实售电无价值。金额结算复用 DeterministicImportCostCalculator/DeterministicExportRevenueCalculator，终值复用既有 TerminalEnergyValueCalculator。此前“尚未确认售电价”的准备状态由本次源码证据关闭。

先基线捕获，再接口/兼容/比较专项；继而原日/联合/旧Demo/相关、Campaign、全项目、Ruff/format/mypy及冻结diff。所有运行独立D盘目录、明确stdout/stderr/JUnit/exit与命令；失败保留，不静默跳过。独立非实现者复核且声明是否运行测试。全通过后本地范围提交，D盘增量归档+基线依赖清单+SHA256；用已验收基线包加增量在新目录还原、核对HEAD与导入并复测专项。无push、发布、设备连接，非异机恢复。

## 2026-10-14 修复后实际门禁与结果

以下是新增实测证据，不沿用旧3046或首轮31/4结果。运行根为上文strategy-capability-repair目录；每个门禁目录保存stdout.log、stderr.log、manifest.json、exit.txt，pytest另有junit.xml。manifest记录完整解释器、参数、工作目录与起止时间。所有成功pytest的JUnit均为0失败、0错误、0跳过。

|目录|实际命令/范围|终态|退出码|
|---|---|---|---:|
|00-before-repro|pytest test_joint_strategy_adapter.py::test_pcs_overrequest_minimal|1 failed；约束后4.1与应为3的断言失败|1|
|01-repaired-focused|两份新策略测试|1 collection error；参数名request被pytest保留|1|
|02-repaired-focused|python -m pytest 两份新策略测试 -q|48 passed，15.72s；仅将保留参数名改为requested|0|
|03-compatibility|verify_strategy_compatibility.py 原9份baseline|18 EXACT_MATCH，先验SHA再逐字段精确比较|0|
|04-predecessor-related|原日适配器/集成、39项联合、旧Demo、time_energy、sidecar、closed_loop、dynamic、interlock、curtailment共10文件|253 passed，18.13s|0|
|05-campaign|python -m pytest test_residential_campaign_a.py 至 f.py -q|62 passed，398.57s|0|
|06-full|python -m pytest -q|3094 passed，443.55s|0|
|07-static-ruff|python -m ruff check --no-cache .|B905相邻zip需显式长度语义、E501错误信息超长|1|
|07-static-ruff-final|同上|All checks passed|0|
|07-static-format|python -m ruff format --check --no-cache .|861 files already formatted|0|
|07-static-mypy-project|python -m mypy --cache-dir 独立D盘目录|393 source files，无问题|0|
|07-static-mypy-scope|显式列出7个Python文件|同一模块被识别为两个包名，未完成类型检查|1|
|07-static-mypy-scope-explicit|同范围加--explicit-package-bases，独立缓存|7 source files，无问题|0|
|07-post-style-focused|两份新策略测试|48 passed，16.84s|0|
|08-comparison|python -m tools.joint_strategy_comparison --output-dir 独立comparison目录|24组场景审计均PASS；3600/60/15秒指标在预定容差内|0|
|09-explanation|explain_strategy_comparison.py comparison目录|仅后处理：中文表格、4份动态命令追踪，无新仿真|0|

所有pytest均带本门禁专用D盘--basetemp、-p no:cacheprovider与--junitxml。全项目之后只修正相邻片段zip为等长切片加strict=True，以及拼接等价错误字符串；不修改计算逻辑，修正后重跑48项专项。原失败与各次静态失败日志均保留。未额外重复运行pre-commit中的全量测试。

输入SHA256：3b37c192d720b4f9608693240ee87643b1ed9f7dabc55653baa3d3a1c32cc10a。修复前原始4.1 kW请求、PCS实际3、PV5、负载0.9导致1.1 kW馈网；修复后同一理想片段原请求仍4.1，命令/实际3，PV交付3.9，电网0。没有改基础策略或抹除能量。

基础策略original/dynamic日馈网由失败候选1.8581418129 kWh降至0.04861403509 kWh，仍有5次真实动态馈网、累计317.1035088秒、峰3 kW，均按原逐事件预算审计。ideal日残余1.850371708e-18 kWh为数值舍入，仍如实留账。修复后original两策略实际物理指标相同；原joint默认/显式与修复前18次完全一致，未替换golden。

reserve/dynamic中，联合/基础策略购电分别22.80991644/17.63169444 kWh，期末库存10/8.761403509 kWh；保电缺口时间积分3.253670365/28.52807286 kWh·h。联合策略增加购电、损耗与弃光，换取较小软目标缺口和更多期末库存；它仍有许可撤销响应期网充0.05833333333 kWh（70秒，3 kW峰），不能写成绝对禁止期间零网充。两者示例净费用14.00004090/11.97199861 CNY；终值敏感性另列，不宣称现实收益或唯一赢家。

独立非实现者capability_coordination_review已只读核验代码、48项终态及18次精确兼容，未亲自运行测试。最后的全量/静态/结果报告复审与恢复回执放在本轮外部证据目录；本文件不提前宣称尚未发生的本地提交、恢复复测或任何远端发布。
