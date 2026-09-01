# EOS Project Constitution（建议治理文档）

> 状态：治理基础草案，不通过本文件自行改变代码合同、用户授权或发布权限。用户当前授权始终优先。

## 1. 两类冲突的优先级

### 1.1 规范意图冲突

当“应该做什么、允许什么”发生冲突时，只按以下完整顺序解释：

1. 用户当前授权；
2. Project Constitution；
3. Master Charter；
4. 已批准 ADR；
5. Specification；
6. Validation Contract；
7. Worker Task；
8. 普通说明。

### 1.2 实际状态冲突

当“现在实际是什么状态”发生冲突时，只按以下完整顺序判断：

1. 当前 Git/GitHub 实时状态；
2. 可复现命令输出与 hash；
3. 独立 reviewer；
4. CI；
5. worker report；
6. Manager 台账；
7. 历史对话。

两张表不得混合使用。任何冲突不得静默选择；必须停止，说明差异、引用可复现证据，并提出最小修复或需用户决定的方案。

## 2. 工程宪法原则

- **evidence-before-claim**：测试、CI、mutation、生成物和发布状态必须与主张相匹配。
- **fail closed / no replay**：边界异常拒绝执行；故障恢复和历史 evidence 不自动提交历史命令。
- **single writer**：execution authority、prepared step、tick 和生命周期记录不可复制、不可重放。
- **bounded scope**：只实现被授权阶段；不以修复为名增加协议、网络、线程、持久化或硬件能力。
- **independent review**：实施者结论不是独立证据；重大 authority 变化需独立检查和必要 mutation。
- **reproducibility**：结论需保留可定位输入、命令、终止摘要和 exit code；collection 不是 PASS。
- **freeze**：冻结链路及 Campaign 数值不得被未授权改动。
- **honest boundary**：仿真、fake 或 transport-neutral 原型不得叙述为硬件、HIL、现场或产品认证。

## 3. 权限角色

| 角色 | 可以做什么 | 不可自行做什么 |
| --- | --- | --- |
| 用户 | 授权阶段、外部写入、发布与合并，指定停止条件 | 被系统或代理替代授权 |
| Manager | 建立计划、台账和 gate，分配有界任务 | 扩大用户未授权范围 |
| Worker | 在限定 worktree 内实施、验证并报告事实 | 自行发布、合并或改变治理权力 |
| Reviewer | 独立只读核验、提出 finding | 修改被审对象或批准自身 finding |
| Publication executor | 按用户明确授权执行受控 push/PR/merge | 以历史授权推断新的共享分支写入 |

## 4. Level 0–3 change control

| Level | 示例 | 最低要求 |
| --- | --- | --- |
| 0 | 只读调查、解释、文档措辞核对 | 清楚说明无状态变更 |
| 1 | docs-only、测试强化、局部工具 | 有界范围、diff/check、相应审阅 |
| 2 | 新的边界合同或生产组合能力 | capability-gap review、focused/upstream/frozen validation、mutation、独立审阅 |
| 3 | 真实 transport、协议、持久化、HIL、硬件或现场能力 | 单独阶段授权、风险分析、接口/安全证据及发布 gate |

Level 不能由实施者自行下调；疑义按更高等级处理。

## 5. Worktree、测试与 finding 制度

- 每个可写阶段在明确分支/worktree 中工作；保留无关现场，不使用 reset、clean 或覆盖性 checkout。
- 不使用 `git add .`；暂存和提交必须逐路径、可审计。
- 长测试必须串行；记录最终 summary 和真实 exit code。超时、无日志或 collection-only 都不是 PASS。
- mutation 只能在隔离临时 worktree 进行，必须还原或删除并证明正式工作树未变。
- finding 按 BLOCKER/MAJOR/MINOR/INFORMATIONAL 记录最小复现、影响、关闭证据与剩余风险。
- skip/xfail、生成物、敏感数据、绝对个人路径、token、credential、代理地址必须在发布前显式扫描；不将临时日志或身份资料写入长期文档。

## 6. 文档、数据与发布

- ADR、specification、validation、Demo、架构说明和学习材料描述同一事实时必须互相一致。
- `docs/governance/` 持久化治理边界；它不替代用户即时指令，也不作为未来阶段的自动授权。
- pre-commit 只有在全部 hooks 实际完成且 exit code 为 0 时才是 PASS；环境阻塞应如实标为阻塞。
- push、PR、Ready、review approval 和 merge 是独立外部写入；每一步均需相应明确授权与当时的 gate 事实。
- 完成定义为：范围、证据、审阅和发布状态均准确；不是“代码看起来完成”。

## 7. 修宪

本宪法的实质修改是 Level 2 治理变更：需要用户明确批准、变更理由、影响范围、相互引用文档更新与独立复审。当前文件本身仅为持久化草案，并不构成修宪行为。
