# 零上网与弃光 opt-in 示例验证记录

## 范围

- 基线设计提交：`71a192ab6ca8f2759aeafa8bb0a19898141ccc05`。
- 只新增 `examples/virtual_home_storage_zero_export`、对应集成测试、文档和 README 入口。
- 默认 EMS runner、策略、`ZeroExportBoundary`、feasibility、handoff、Simulator 模型和
  ledger 均未修改。
- 所有结果为虚拟仿真，不代表 PCS/BMS、HIL、设备 ACK、真实弃光或现场零上网。

## 关键实现证据

- 显式 `curtailment_allowed=True` 才能生成弃光后的 PV/Grid result。
- Battery/Load 先由现有纯模型 preview；REJECTED 返回 `simulation_trace=None`，没有可
  提交的 next SOC、progression 或 ledger。
- available/utilized/curtailed PV 分开保存，原 `PVSimulationInput` identity 不变。
- 功率 oracle：`A=U+C`、`G=L+B-U`、`G>=-E`。
- 能量 oracle：各功率乘 exact duration，并独立核对相同平衡；电池效率继续只由现有
  Battery next-SOC 表达。
- 电池放电造成且 PV 弃光无法修正的出口返回
  `NON_PV_EXPORT_CANNOT_BE_CORRECTED`，不反转或修改电池 action。

## S09 代表结果

Schedule 与 Economic 默认 trace 都保持 `PV actual=10 kW`、`Battery actual=0 kW`、
`Grid=-10 kW`。显式 opt-in 后，两条路径均得到 `PV utilized=0 kW`、
`PV curtailed=10 kW/10 kWh`、`Battery actual=0 kW`、`Grid=0 kW/0 kWh`。

运行命令：

```bash
/workspace/eos-cloud-prep/venv/bin/python \
  -m examples.virtual_home_storage_zero_export.demo \
  --output-dir /tmp/eos-zero-export-opt-in
```

## 验证结果

16 个命名场景及跨策略 lineage 反例由 41 个独立断言/非法输入探针覆盖；focused
测试为 `41 passed`。相关 ZeroExport、Simulator、24 小时示例和缺陷 Campaign 回归为
`485 passed`。仓库级 Ruff、867 文件格式检查和 Mypy 506 个源文件通过；最终 lineage
加固后又对 3 个变更源/测试文件复跑 Ruff 与 Mypy。唯一一次完整回归为
`3061 passed in 420.40s (0:07:00)`，其后没有重复全量运行。

Fresh-context 只读审查发现并促成了三项加固：feasibility 必须经 exact
provenance→feasible→handoff→actuation 链绑定 caller 的 source step；机器可读输出每行
携带 `evidence_kind=SIMULATED` 与 `telemetry=false`；Z12 必须由真实
`SimpleBatteryPhysicsModel` preview 产生部分 headroom 结果，而非手工构造 Battery
result。三项均有直接回归测试。

最终教学输出 SHA-256：

- JSON：`6c330c6b145dfc1fe96fe8ab3b1b9c3af291c4641a4f5146b2d7c4cd3f53fe95`
- CSV：`a8428b851fd999799c1291a903f8c17d566d10f2a367ed0013ca1f0c6b7969b3`
- 中文报告：`e30cd9ea1a711223610d0edcfa312ceb874c06e38ce944521ad554d44370744f`

最终 fresh-context 只读复核结论为 **NO FINDINGS / 无阻塞**。审查者真实重放了把
Economic feasibility、provenance 与 handoff 整套传给 Schedule source step 的反例，
确认以 `source_handoff must preserve exact battery actuation` fail closed；并独立复跑
focused 41 项、目标 Ruff/format/Mypy、S09 两策略输出与手算功率/能量核对。相对设计
基线的 core diff 为零。
