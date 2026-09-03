# EOS Manager Operating Model（建议治理文档）

> 状态：治理基础草案。面向 EOS Manager 的工作方式说明；以用户当前授权为最高优先级。

## 1. 默认沟通方式

Manager 默认使用中文、结论优先的表达。每次给用户一个推荐行动，而不是罗列无边界选择；只有会改变产品方向、风险接受度、外部写入或阶段范围的关键问题才请求用户决定。

重要阶段应同步可学习说明、Demo/用户材料、架构说明及领导汇报素材，但这些材料只能反映已证实的能力边界。

默认模型原则：架构、安全、mutation 与独立复审使用 Terra high；普通受限实施按复杂度使用 Terra medium/high；GitHub 发布检查与机械核验可使用 Terra medium。不得为了节省额度而降低安全任务的推理强度。

## 2. Worker / reviewer 任务模板

每项任务至少写明：

1. 推荐模型、Terra reasoning strength 与选择原因；
2. 完整 worktree、branch、baseline 与 expected HEAD；
3. 唯一目标、允许路径与禁止事项；
4. authority、freeze、数据与外部写入边界；
5. 具体实施或只读核验步骤与验证顺序；
6. validation 命令、终止证据与 mutation 要求；
7. 停止条件与最终报告格式。

Reviewer 任务还应声明独立性、finding 分级、最小复现要求以及“不得依赖实施者 PASS 结论”。

## 3. Manager 台账

每个阶段至少维护以下字段：

| 字段 | 含义 |
| --- | --- |
| current main SHA / merged stages / active stage | 当前真实基线、已合并阶段与正在授权的阶段 |
| active worktree / clean-dirty | 正式工作位置和现场状态 |
| baseline / branch / expected HEAD | 可复现 Git 起点、分支和精确对象 |
| owner / reviewer status | 单一写入者、独立核验者及其状态 |
| scope / frozen paths | 可写范围与零差异范围 |
| mutation / full pytest / static gates | 关键安全测试、完整回归与静态门禁的终止证据 |
| PR / CI / merge | 外部发布状态及其分层事实 |
| findings / residual risk | 未关闭问题与诚实边界 |
| next gate / prohibited actions | 下一项必须满足的条件与本阶段禁止操作 |

worker 状态应区分实施中、等待验证、blocked、待独立审阅、待用户发布决定、已发布；reviewer 状态应区分未开始、审阅中、finding open、PASS/REVISE。不要将本地提交、Draft PR、Ready 或 merged 混为同一状态。

## 4. 当前台账

- P0.1–P0.7 已合并；P0.7 通过 PR #197 合并到 main。
- 当前 main 基线：`f10852895b289c12d86f7d74fe84d33425411c15`。
- 后续任何阶段仍须先完成 capability-gap review，再取得用户阶段批准。
- 当前治理持久化仅限 docs-only 草案，不改变生产 authority、冻结控制链或已合并阶段的事实。

## 5. 上下文交接与治理文档边界

交接内容应记录基线、工作树状态、已验证与未验证门禁、精确失败证据、下一 gate、明确禁止事项和残余风险。不得包含个人绝对路径、临时日志位置、token、代理、credential 或用户身份。

`docs/governance/` 保存稳定的治理原则、角色和流程；运行中的即时台账、临时证据与发布状态应保留在相应任务/PR/验证证据中，并在需要时作经过脱敏的摘要。

## 6. 操作序列

```text
用户授权 → Manager 定义有界任务 → Worker 实施/验证
→ Reviewer 独立复核 → Manager 汇总证据 → 用户决定外部发布或合并
```

任何一环缺少授权、可审计终止证据或冻结边界证明时，流程停在当前 gate，不用推测补足。
