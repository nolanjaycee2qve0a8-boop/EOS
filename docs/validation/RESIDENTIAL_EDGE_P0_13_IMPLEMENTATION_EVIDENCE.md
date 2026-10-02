# Residential Edge P0.13 第一批实现与本地验证证据

状态：第一版独立初审为 **REVISE**；R1 在原五个文件内完成修复及作者验证，本文件为交同一 reviewer 复核的冻结送审快照。
没有 push、PR、合并或发布；第一版 REVISE 不构成审核通过，R1 复核结论见追加记录。本文件不改写已合并的候选合同。

## 授权、基线与范围

用户在主对话批准“序号严格递增，允许显式声明的跳号”的推荐规则，并在主对话确认第一批实现、测试后先独立审核、不合并发布后回复“好的去做吧”。本次委托再次明确授权新增审计器、测试与专属验证记录。

- 核验日期：2026-10-02 UTC。
- 仓库：`/workspace/EOS`，origin 为 `https://github.com/nolanjaycee2qve0a8-boop/EOS.git`。
- 起始 HEAD 与本地 `origin/main` 均为 `a843d25a7f215f49ea677025416c2485558429cf`；起始 `git status --short` 为空。
- 本地分支：`feat/p0-13-scope-handoff-audit`。没有访问或改变远端引用；远端实时状态不作额外声明。
- 核验根目录、workspace、仓库，未发现适用的 AGENTS.md 或 `.agents/skills/*/SKILL.md`。
- 使用 `/workspace/eos-cloud-prep/venv/bin/python` 及同目录工具，不使用旧 `.venv`。此前 2800 项基线测试不重复；下述 full pytest 检验本次新状态。
- 仓库惯例是根目录 `edge_runtime/`，没有 `src/edge_runtime/`。

仅新增：

1. `edge_runtime/device_fact_command_correlation_scope_handoff/__init__.py`
2. `edge_runtime/device_fact_command_correlation_scope_handoff/contracts.py`
3. `edge_runtime/device_fact_command_correlation_scope_handoff/evaluator.py`
4. `tests/unit/edge_runtime/test_device_fact_command_correlation_scope_handoff.py`
5. 本文件。

ADR-101、P0.13 candidate specification、P0.13 candidate validation plan 均已读取并保留原文；P0.1–P0.12、Residential、Campaign A–F、Manager 台账、依赖及 CI 均不改动，不启动第七册。

## 已落实的用户决策与设计说明

`DeviceFactCommandCorrelationScopeFacts.continuity_input` 直接保留一份精确的 P0.12 `DeviceFactCommandCorrelationContinuityInput`，包括调用者自己的有序 P0.11 inputs、原始 P0.12 scope declaration、assessment identity、as_of 和 maximum_age。没有复制一套成员范围摘要作为替代事实。

外层必须提供恰好两个 scope facts。对形状正确的每份原始 P0.12 request，调用现有 `DeterministicDeviceFactCommandCorrelationContinuityAuditor.evaluate` **恰好一次，并传入原对象**。结构错误的载荷直接 GAP；结构正确但前置规则不通过的 scope 委托后产生 P0_12_GAP。第一个 scope GAP 不阻止另一个结构有效 scope 被审计。只有两者都 PASS，才进入交接判断。P0.13 不复制或重写 scope 内 sequence/time/freshness/ACK/actual 规则。

声明必须给出两个有序的精确 P0.12 scope declaration。这一对声明逐字段表达 scope identity、origin 和完整六字段 source/epoch relationship 的允许关系；允许显式改变 origin/source/epoch，但不会由此推断 reboot/disconnect/reconnect。

声明还给出前 scope 实际最后一项、后 scope 实际第一项的 assessment identity、transaction sequence、assessment time，以及 `sequence_advance`、`time_advance` 和 `member_identity_relationship="distinct"`。该最小版本只支持 distinct：所有 P0.11/P0.12/P0.13 assessment identity 全部不同；所有成员 transmission identity 不重复；所有 actual observation identity 不重复。不同 identity domain 不互相混用。

- **序号**：实际 initial 必须大于 terminal，差值等于调用者声明的正整数；bool、浮点、缺失或不匹配都 GAP。`10 → 12` 声明 `sequence_advance=2` 可 PASS；没有默认 `+1`，声明为 1 或缺失都 GAP。
- **时间**：实际 initial assessment time 严格向前，差值等于调用者声明的正 timedelta；没有系统时钟、默认容差或默认 freshness。所有成员时间及两份 P0.12 assessment as_of 都必须不晚于新的 P0.13 as_of，且在显式 maximum_age 内（年龄等于上限有效）。
- **范围**：P0.12 已保证各 scope 内有序；检查真实 terminal→initial 即约束两个成员范围不逆序、不重复、不重叠。声明伪造首末边界不能通过。不排序、不补事实、不构造合并的 P0.12 scope。
- **输出**：仅新 assessment identity、as_of、PASS/GAP、不可变 findings。findings 仅含 scope_index、闭合 gap code、静态说明，不保存 raw input、前置 assessment、活对象或 authority。
- **公共拒绝方式**：有效外层 envelope 中的缺失/错误事实产生 GAP；无法提供新 identity/as_of 的外层错误类型直接 TypeError，构造错误 envelope 产生 TypeError/ValueError，沿用前置边界模式，不捏造 identity 或时钟。合法接收的事实是 frozen/slots 的精确公共类型；非法嵌套 object 槽位允许表达 GAP，不代表接受其 authority 或深度不可变性。

PASS 只说明有限 caller facts 满足声明。ACK 不表示物理完成，actual 不替代 P0.3 reconciliation；没有 command/device/runtime/adapter/session/continuation/transport/execution/restore/replay 能力，没有网络、设备、线程、调度、重试、持久化或 lifecycle imports。

## 第一版验证记录（保留历史，不代表 R1 或复核通过）

按计划顺序完成以下终态门禁；所有 pytest 都使用预制解释器。除 mutation 故意失败外，下表退出码全部为 **0**。

| 门禁 | 实际终态摘要 |
| --- | --- |
| P0.13 focused | 127 passed in 0.13s |
| P0.10/P0.11/P0.12 frozen relevant | 64 passed in 0.08s |
| all Edge Runtime | 427 passed in 0.50s |
| Residential acceptance/reference/leadership curves | 23 passed in 1.11s |
| Campaign A–F 六个文件 | 62 passed in 392.45s |
| full pytest（本次实现状态） | **2927 passed in 423.90s** |
| Ruff check 全仓 | All checks passed |
| Ruff format --check 全仓 | 836 files already formatted |
| mypy 仓库默认范围 | no issues found in 383 source files |
| mypy P0.13 三模块与测试 | no issues found in 4 source files |
| public surface/import allowlist AST assertions | 1 passed in 0.05s |
| frozen/sensitive/generated-output scan | tracked 文件相对基线零差异；仅五个允许新增文件；凭据/私钥模式无匹配，无新增生成输出 |
| pre-commit --files 五个新增文件 | Ruff check / format / mypy Passed；pytest Skipped，命令总退出码 0 |

pre-commit 使用 `PATH=/workspace/eos-cloud-prep/venv/bin:$PATH`、`PRE_COMMIT_HOME=/workspace/.cache/pre-commit`、`SKIP=pytest`；只给出五个新文件，保护所有旧文件。pytest hook 明确跳过重复昂贵的 full suite：刚完成的 full pytest 对应四个 Python 文件 SHA-256 与 pre-commit 后、最终交付一致。没有把 Skipped 写成 Passed。Python 为 3.12.14，pytest 8.4.2，预制 Ruff 0.16.10、mypy 1.20.2；pre-commit 钉住的 Ruff 0.12.4、mypy 1.16.1 也通过。依赖/CI 配置没有改动。

开发过程中初次 Ruff/mypy 提示了行宽、import 排序和测试辅助对象的类型标注问题，已修正；上表是最终源码的终止结果。没有重跑最初的 2800 项干净基线全套。

### 九类 semantic mutation 的真实证据

临时隔离 worktree：`/tmp/eos-p013-mutations`，detached 于同一基线；仅复制本次源码与测试。通过实际模块路径断言确认 import 来自该 worktree，隔离控制组 **127 passed**，退出码 0。每个 mutant 独立恢复原始源码后只改一个语义点，运行指定现有测试；测试文件不随 mutant 改写。下列 **16/16** 均出现 `AssertionError`、pytest 退出码 **1**。无语法/收集/fixture 错误充当击杀；没有人工构造最终 PASS/GAP 作为 mutation 结果。类别 9a 使用实际 AST 白名单断言，非静态 grep。

| 类别 / 探针 | 退化与断言 |
| --- | --- |
| 1a / 1b | 删除 P0.12 委托：精确调用次数断言失败；忽略真实 P0.12 GAP：scope 内重复 sequence 的真实输入被错误放行，GAP 断言失败 |
| 2a / 2b | 删除 scope identity/origin 比较、删除跨 scope 成员 identity 唯一性：对应失配/重复事实断言失败 |
| 3 | 保留 scope identity/origin 比较但移除 source/epoch 比较：六个字段各自失配均被断言击杀 |
| 4a / 4b / 4c / 4d | 分别移除真实边界、sequence、time、freshness gate：伪边界、逆序/重复/重叠、过期/未来断言失败 |
| 5 | 删除 duplicate scope gate：两个不同 raw scopes 同 identity 且声明匹配时被错误放行，断言失败；历史 assessment/序列化/摘要拒绝另由 focused matrix 覆盖 |
| 6 | source/epoch 变化被错误推断为 reboot GAP：完整显式声明的合法变化本应 PASS，断言失败 |
| 7 | 用 ACK availability 自动补 actual availability 后再交给冻结审计器：真实 actual unavailable 的 GAP 被错误修复，断言失败；P0.3 reconciliation 伪事实拒绝另由 focused matrix 覆盖 |
| 8a / 8b | 加跨调用 seen registry：重复合法输入确定性断言失败；输出增加 raw_facts 槽位：严格输出字段断言失败 |
| 9a / 9b | 引入 socket import：AST 公共依赖边界断言失败；放宽 exact raw-input type 接受带 execute 方法的 subclass：authority 类型拒绝断言失败 |

这证明列出的具体突变被捕获，不宣称穷尽全部可想象的错误。隔离 mutation 源码在结束时恢复到交付版本，原工作区与冻结阶段未被 mutant 修改。

### 复现与交付

全部命令参数、终态 exit code、测试摘要见仓库外 `/workspace/eos-p013-review/validation.json`、`finish-checks.json`、`mutations.json` 与 `logs/`。`validate.py` 记录分层回归和静态检查；`mutate.py` 保存隔离 runner；`mutants/` 保存每个具体变体。日志不加入仓库，避免扩大授权范围。

- 精确新增差异：`/workspace/eos-p013-review/p0.13-scope-handoff.patch`。
- 文件及 patch 的 SHA-256：`/workspace/eos-p013-review/SHA256SUMS`。
- full pytest 时及最终 Python 文件哈希：`full-pytest-source-sha256.json`、`validated-code-sha256.json`。
- 最终基线/新增路径/补丁可应用性核验：`logs/final-integrity.log`。
- 仅五个新增文件，零删除、零旧阶段修改；HEAD 保持基线，无本地 commit、push、PR、merge 或发布动作。

补丁是在未暂存的新文件上生成的，`git diff` 默认不会显示它们；独立复审应读取 patch 或这些新文件，勿将默认空 diff 误认为无交付。

## 第一版能力界限与独立复审交接（原记录）

无 provenance registry、跨调用 state 或 persistence，**不能证明事实来自当前调用者、不能证明跨调用 scope reuse、不能识别人为重新包装成合法 P0.11/P0.12 raw inputs 的历史事实**。实际历史 assessment 对象、序列化 assessment、摘要以及错误类型会被拒绝；对合法 raw inputs 的来源无证明能力。调用者重复提交合法输入会得到同样结果，这是确定性，不是授权 replay 或后续 delegation。

Python frozen dataclass 是惯例性不可变证据，不是抵御 `object.__setattr__`、任意进程内 monkeypatch 或恶意 Python 运行环境的安全沙箱。新 assessment identity 的唯一性仅在当前 input 内核验，不承诺跨调用全局唯一。

本批测试与 mutation 由实现者执行。独立临时 worktree 的 mutation 隔离不等于独立人员/agent 复审；主对话需要安排独立 authority review，再决定后续动作。复审应重点核对精确委托次数、范围与跳号决策、时间规则、输出无 authority、来源证明边界，以及冻结阶段零差异。此处停止，不启动发布流程。


## R1 修订：响应独立初审 REVISE

初审 reviewer 为 `/root/p013_independent_review`，新独立上下文、共享执行器；完整报告和原始反例位于 `/tmp/eos-p013-independent-review-6iwmaafv/`。初审发现两个 P1（DST 绝对时刻误判、自定义 tzinfo 深层保留 raw/authority）和一个 P2（嵌套容器/标量子类绕过 inert 边界或抛异常），并得到 7 failed / 1 control passed。R1 又在哈希匹配的第一版隔离副本重放原脚本，确认为同样 7 failed / 1 passed，退出码 1。第一版五文件快照存于 `/workspace/eos-p013-r1/initial-revise/`；第一版 patch、原验证日志和初审报告保持原样。上文第一版通过记录并不覆盖这些真实失败。

修复没有修改三份已合并合同或 P0.1–P0.12。P0.13 原合同要求 inert immutable facts、错误类型拒绝以及实际时间严格向前；允许携带 authority 的自定义值、错误 DST 时刻曾被接受是实现缺陷，不是获准的接受域。本次没有给冻结 P0.12 增加规则，也没有将其输入复制/转换后再审计。

- 所有 P0.13 声明时刻相等、交接方向、精确差值、future/stale 检查使用整数 ordinal 与微秒构成的绝对时刻坐标，再减去已验证的标准时区 offset。无浮点 timestamp、系统时钟或默认容差；避免 datetime.min/max 转 UTC 的溢出。
- 时间表示只接受精确 datetime 搭配精确 `datetime.timezone` 或非文件流来源的 `zoneinfo.ZoneInfo`；先校验类型，再调用可信标准类型行为。固定时区的 name/offset、ZoneInfo 的 key 也检查为惰性精确内建值。拒绝自定义 tzinfo、时区子类及携带任意对象的内部值，不先调用其 hook 再“清洗”。标准 UTC、固定偏移、合法 ZoneInfo、DST fold 正向交接和等价 UTC 声明均有控制例。
- `_raw_shape` 在遍历前要求精确 tuple；对已识别的精确 dataclass 槽位检查原始叶子表示，拒绝 str/int/float/timedelta 等子类。类型判断使用 `is`，不调用自定义 metaclass 相等运算。不递归遍历未知对象，不 catch-and-repair 前置语义。结构有效 scope 的原对象仍恰好委托一次；另一无效 scope 不阻止有效 scope 的一次审计。
- 不可信外层时间使 Input/Assessment 构造器 TypeError；不可信嵌套事实/声明产生 GAP。输出仅保留经 inert 类型边界验证的时间对象，不通过自定义 tzinfo 持有 raw facts。此方式没有执行不可信 hook，也没有将非法值默默规范化为合法事实。

原审核脚本原样在 R1 上重跑为 **7 passed、1 failed**：唯一失败是原 tzinfo 测试假设自定义时区应先获得 PASS，现在在构造阶段 TypeError。原脚本不修改。另在仓库外副本只将这项预期调整为明确拒绝，得到 **8 passed**，退出码 0。正式测试覆盖相同拒绝语义，并用会抛 AssertionError 的 hook 证明其没有被调用。两组实际日志分别保留于 R1 的 `logs/original-review-verbatim.log` 与 `logs/review-rejection-expectation.log`，不将原脚本宣称为全通过。

补查还复现了精确 `ZoneInfo.from_file` 可保留调用者文件 repr 的字符串子类，公开 key 为 None 或普通 str 也不足以保证 inert。R1 在调用任何时区行为前用精确内建 ZoneInfo 的表示检查拒绝这种不透明来源；仅检查返回能力，不执行重建、pickle 读写或持久化。普通 ZoneInfo/ZoneInfo.no_cache 的合法 key 支持不变；文件流构造的时区全部拒绝，隐藏 repr 不会被调用，也不会随输出保留。新增回归以 weakref 证明该内建时区确实持有隐藏 payload，再断言 P0.13 拒绝。

为补足该缺陷，第一次 R1 full pytest 在未完成时主动终止，实际进程退出码 **-15**，耗时约 104.7 秒；不是通过，也不是测试断言失败。此前 Campaign A–F 已完成 **62 passed in 403.63s**。该轮源码哈希、命令和日志存于 `attempt-1/`。修正后重跑 focused、前置、Edge、Residential、完整 pytest 和静态门禁；单独 Campaign 不再重复，其冻结文件未改变，最终 full pytest 会再次覆盖 Campaign。不会把中断记录写作终态通过。

### R1 送审快照的终态验证

以下为修订后的终态摘要，退出码均为 0。所有命令用预制解释器/工具；完整命令与日志位于 `/workspace/eos-p013-r1/`。第一版记录及初审反例没有覆盖或删除。

| 门禁 | 实际结果 |
| --- | --- |
| focused | 169 passed in 0.18s |
| predecessors | 64 passed in 0.07s |
| edge-runtime | 469 passed in 0.55s |
| residential-frozen | 23 passed in 1.13s |
| full-pytest | 2969 passed in 435.80s (0:07:15) |
| ruff | All checks passed! |
| format | 836 files already formatted |
| mypy-repository | Success: no issues found in 383 source files |
| mypy-p013 | Success: no issues found in 4 source files |
| 原反例按当前明确拒绝策略复核 | 8 passed；原样脚本 7 passed / 1 TypeError 失败另列保留 |
| 公共边界 AST 断言 | 1 passed |
| pre-commit | Ruff/format/mypy Passed，pytest 明确 Skipped；同哈希 full pytest 复用 |

单独 Campaign A–F 的 62 passed 是本轮前一候选已完成的冻结回归，记录在 `campaign-prior.json` / `attempt-1/`；后续修改仅涉及 P0.13 类型边界与新测试，最终 full pytest 又覆盖了全部 Campaign 测试，未重复单独昂贵运行。

R1 的 **27/27 isolated semantic mutants** 全部被真实断言击杀，每个 pytest 退出码 1。原 16 个在修订源码上重新执行；新增 11 个覆盖忽略绝对 offset、回退墙上时间声明/freshness、调用自定义 timezone hook、遗漏固定时区 name/offset 与 ZoneInfo key/file-repr 边界、接受 tuple/数值子类、执行 metaclass 相等方法。异常预期断言 `DID NOT RAISE` 与普通 AssertionError 均计为真实断言；语法/收集/fixture 错误不计击杀。`mutate.py`、`mutants/`、`mutations.json` 与逐项日志保留具体变体和终态。

补丁：`/workspace/eos-p013-r1/p0.13-scope-handoff-r1.patch`；完整五文件及补丁 SHA-256：同目录 `SHA256SUMS`。终态核验为旧 tracked 文件相对基线零差异，且仅原五个新文件；补丁能够重建完全一致的五文件。四个 Python 文件与 full pytest / pre-commit 的源码哈希完全一致。

本节是作者完成验证后的**冻结送审快照**，不预写 KEEP。同一独立 reviewer 将在新回合复核；其结论与反例、命令、前后哈希单独留存，以最终答复链接的独立报告为准。审核期间作者不修改此五文件。


## R2 修订：完整跨 scope 时间范围

R1 独立复核仍为 REVISE，仅剩一个 P1：纽约回拨日各 scope 可按冻结 P0.12 的墙上时间规则 PASS，实际 terminal→initial 也向前，但其他成员的绝对时间导致两个范围交叠。完整独立报告与 16 种 fold 组合反例存于 `/tmp/eos-p013-independent-r1-kgu3akxq/`；5 failed / 15 passed（包括四个合法控制）。原 R1 五文件另存 `/workspace/eos-p013-r2/r1-revise/`，原记录均保留。

合同规格第 21、25、35、39 行已经要求从成员集合确定范围并拒绝跨 scope 冲突，故本次补实现缺失，不更改已合并合同。两份真实 P0.12 均 PASS 后，P0.13 用绝对时刻检查前 scope 最大成员时间严格小于后 scope 最小成员时间，结合原有真实索引 terminal→initial 声明、精确差值和 freshness。只读扫描求 max/min，不排序、不合并 scope、不修复事实，也不重审 P0.12 的 scope 内部顺序。新增控制显式允许 P0.12 PASS 且内部绝对倒序但两个完整范围分离的输入，防止越界收紧冻结阶段。

正式回归新增 16 种 fold 组合及一个内部顺序控制，独立 oracle 使用 UTC 转换（生产实现仍用整数绝对坐标）。新增 mutation 只删除完整范围关系，应被这些真实断言击杀。修复仍只涉及原五个新增文件，未引入依赖、网络、设备写入、执行 authority 或跨调用状态。无 provenance registry 的能力界限继续适用。

### R2 作者终态验证及冻结交接

下列实际门禁退出码均为 0；完整命令、原始日志和各文件哈希位于 `/workspace/eos-p013-r2/`。

| 门禁 | 实际结果 |
| --- | --- |
| focused | 186 passed in 0.18s |
| predecessors | 64 passed in 0.10s |
| edge-runtime | 486 passed in 0.63s |
| residential-frozen | 23 passed in 1.26s |
| full-pytest | 2986 passed in 445.68s (0:07:25) |
| ruff | All checks passed! |
| format | 836 files already formatted |
| mypy-repository | Success: no issues found in 383 source files |
| mypy-p013 | Success: no issues found in 4 source files |
| 独立审核反例/控制的作者重放 | 28 passed |
| 公共边界 AST | 1 passed |
| pre-commit | Ruff/format/mypy Passed；pytest 明确 Skipped，复用同哈希 full pytest |

原 27 项和新增完整范围门禁共 **28/28 semantic mutations**，全部在隔离副本由真实断言击杀，pytest 退出码均为 1。新增变体只删除 max/min 范围条件，复现 5 failed / 11 passed；没有以静态 grep 替代语义反例。

本轮 full pytest 包含 Campaign A–F；未再次单独重复 Campaign 的昂贵运行。此前单独 Campaign62、R1 full2969、初次中断 -15 与各轮 REVISE 均保持独立历史记录，不混作本轮成功。

本轮精确补丁为 `/workspace/eos-p013-r2/p0.13-scope-handoff-r2.patch`，五文件及 patch 的 SHA-256 为同目录 `SHA256SUMS`。完整旧阶段 tracked 文件逐字节核验仍为零差异；补丁可重建完全相同的五个新文件。Python 文件与本轮 full pytest/pre-commit 哈希一致。

此为作者冻结送审快照，不预写独立 KEEP。同一 reviewer 在新回合执行复核，独立报告在仓库外留存并由最终答复链接；审核中作者不修改五文件。没有 commit/push/PR/merge/发布或新的 Library 尝试。
