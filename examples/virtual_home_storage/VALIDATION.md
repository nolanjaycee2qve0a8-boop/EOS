# 本地候选验证记录

基线：`bc15c5ad7ec50a4b09d3fbec4f02d7f56bd0c5a8`，从 fresh origin/main
创建 `example/virtual-home-storage`。起点 clean；Git author 与 GitHub 登录身份已核对，
不在长期文档记录个人身份。仓库与父目录未发现 AGENTS.md 或本地 SKILL.md；
已读取章程、宪法、工作规则、贡献指南、CI 和相关冻结 P0.2–7 spec。
用户本次授权优先于旧治理台账的 active NONE；未修改治理文档或冻结语义。

## 可复跑命令

从源码仓库根目录，使用 Python 3.12 开发环境（下列 `python`、`ruff` 等应来自同一 venv）：

```bash
python -m examples.virtual_home_storage.demo --output /tmp/eos-virtual-home-output
python -m pytest tests/integration/test_virtual_home_storage.py -q
python -m pytest tests/integration/test_virtual_home_storage.py tests/unit/edge_runtime/test_controlled_composition_session.py tests/unit/edge_runtime/test_controlled_composition.py tests/unit/edge_runtime/test_controlled_runtime.py tests/unit/edge_runtime/test_device_simulator.py tests/unit/edge_runtime/test_device_adapter.py tests/unit/ems_strategy/test_edge_command_handoff.py tests/unit/ems_strategy/test_ems_self_consumption_strategy.py tests/unit/ems_strategy/test_feasibility_boundary.py tests/unit/ems_strategy/test_decision_provenance.py -q
python -m pytest -q
ruff check .
ruff format --check .
mypy .
mypy examples/virtual_home_storage/demo.py tests/integration/test_virtual_home_storage.py
git diff --cached --check
```

pre-commit 使用可写的 `PRE_COMMIT_HOME` 与同一 venv 的 PATH。
初轮静态 hooks 使用 `SKIP=pytest pre-commit run --all-files`，pytest hook 为
**Skipped**，不称为全部 hooks PASS。独立复审修正测试后，最终门禁改为
`pre-commit run --all-files`（不设置 SKIP），由 pytest hook 执行最终完整测试。
新文件逐路径暂存，以确保 all-files 包含它们；未提交、push、PR 或 merge。

## 失败历史（不将失败补记为通过）

1. 首次 CLI exit 1：输出字段访问 `EMSStrategyDescriptor.strategy_id`，实际字段为
   `name`。仅修正 example 的字段读取；再次 CLI exit 0，五场景均产出。
2. 初次 Ruff exit 1：中文全角标点触发 RUF001，另有长行；改为 ASCII 标点并格式化。
3. 初次 focused collection exit 2：参数名 `request` 是 pytest 保留名；改为 `requested`。
4. 第二次 focused exit 1：17 passed / 1 failed，过期测试错误预期 `expired`；
   实际公开枚举为 `command_expired`。核对冻结实现后仅修正测试文本预期。
5. 首次显式 mypy exit 2：examples namespace 导致同文件双模块名；新增
   `examples/__init__.py`。第二次 exit 1：三处类型错误；明确 Literal、fault tuple
   类型和测试 replace 的字段类型，后续显式 mypy exit 0。
6. 首次 pre-commit exit 1：默认 home cache 位于只读文件系统。指定可写
   `PRE_COMMIT_HOME` 后 hooks 可执行；不是代码失败，也未改动系统权限。

7. 独立初审发现 MAJOR：equal-but-distinct metadata 测试实际因
   `LookupError: script exhausted for observation` 失败，而非目标拒绝条件；
   初次 18 项中该项是错误原因的假阳性，不能作为边界证据。ObservedRuntime
   仅记录首个 tick，不能用其 notes 长度证明后续无 tick。修复只改测试：fresh
   runtime、两套显式 adapter facts、被动 composition evidence 记录、精确 ValueError
   cause；现明确验证第二 logical idle tick 的 duplicate_command_id、actual=0、
   SOC 不变、没有第二 transmission。独立复核 18 passed，MAJOR 关闭。
8. 修复前的单独全量已被主动中断（SIGINT）以在最终测试快照重新执行门禁：
   exit 2，1359 passed in 412.97s；不是完整通过，也不是产品故障。中断位置在
   既有 optimizer 测试。最终全量由不跳过的 pre-commit pytest hook 完成，结果见下文。

9. 最终测试快照的 pytest 实际完成 **3004 passed in 412.62s**，但该次
   pre-commit 整体 exit 1：作者在 hook 运行期间将本记录中的 format 文件数从
   844 修正为 845，pre-commit 检出 `files were modified by this hook`。实际 diff
   仅为本记录的一行，demo/test hash 不变；不是 pytest 断言失败。该次不记为
   全 hooks 通过。先固定文档，再执行不并发编辑的最终完整 hooks。

## 已完成验证

- 五场景 CLI exit 0，JSON/CSV 可解析且重复运行字节一致（测试覆盖）。
- focused + 先修回归：243 passed，exit 0。
- 全仓 Ruff check exit 0；最终 format check：845 files already formatted，exit 0。
- 全仓 mypy：503 source files，exit 0；额外显式 example/test mypy：2 files，exit 0。
- 初轮 pre-commit Ruff check/format/mypy Passed，pytest Skipped，进程 exit 0。
- 最终重跑 `pre-commit run --all-files --verbose`：Ruff check、format、mypy、
  pytest 全部 Passed，整体 exit 0；pytest 完整摘要为
  **3004 passed in 434.91s (0:07:14)**。期间没有工作树改动，demo/test hash 与
  独立复核快照一致。完成后仅收尾本验证记录；未改变实现或测试。
- diff whitespace 检查 exit 0。冻结目录 diff 为空；新增测试无 skip/xfail、无 monkeypatch。
- 独立 fresh-context 只读 reviewer（共享 executor，非独立机器）亲跑五场景 CLI、
  手算和拒绝反例；初审发现上述 MAJOR，修复后 focused 18 passed / exit 0。
  代码审查 PASS，无剩余 BLOCKER/MAJOR/MINOR；完整门禁已通过。
- 最终源码实现未变，测试增强；初轮 full 不作最终全量通过证据。

最终源码 SHA256（完整门禁以此快照执行）：

```text
4247a185c12b158a22a9bfeaed04ad45451ea1e399e572310b17e7910056214b  demo.py
593523d488effe64a3f1d631904f8cfaf17f6c316b6fbb12747f7020a2cecb62  test_virtual_home_storage.py
```

只生成临时 JSON/CSV 教学输出，不将 generated data 或本机日志提交到仓库。
最终状态为本地审核候选：8 个文件变更，冻结核心/规格/治理零差异；未提交，
未执行远端 CI、push、PR 或 merge。没有需要扩大实现范围的未决问题。
