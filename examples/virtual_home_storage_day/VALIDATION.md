# 24 小时虚拟家庭储能教学示例验证记录

## 候选身份与范围

- 基线：`origin/main` = `c1956b407c5ea8269182dd96d37936e2f52a666b`
- 分支：`example/virtual-home-storage-day`
- 解释器：`/workspace/eos-cloud-prep/venv/bin/python`（Python 3.12）
- 变更只涉及 `examples/virtual_home_storage_day/`、对应测试、中文指南和
  README 入口；冻结核心实现没有差异。
- 所有输入、actual、SOC、成本和曲线均是模拟事实，不是设备测量或控制证据。

## 首次失败证据

开发过程中保留并修复了以下真实失败，没有修改核心流程或以 monkeypatch 绕过：

1. 新验收测试首次运行时，出口收益期望写成展示用六位小数 `0.531856`，而逐小时
   独立积分的精确值是 `0.5318559556786707`。期望改为精确手算值。
2. Ruff 首次指出新文件长行与全角标点规则；拆分/局部说明后通过。
3. 显式 Mypy 首次指出宽泛 `object` 转换和结果 union 未收窄；增加现有 Economic
   结果类型检查与窄化辅助函数后通过。
4. 首次组合回归命令使用了两个不存在的单元测试文件名，因此退出码为 4、未运行
   测试。改用仓库中的两个真实 integration 文件后，16 项通过。该失败是命令路径
   错误，不是代码失败。
5. ImageMagick 的 SVG delegate 缺少 `rsvg-convert`；改用已安装的 Inkscape 将同一
   SVG 渲染为 980×610 PNG。目视确认六条曲线、图例、共享时间轴和正负功率均清晰
   且无裁切。PNG 仅用于本地复核，不作为仓库产物。
6. 候选冻结前的本地复读发现 SOC 曲线最初按 0%–100% 映射，但图上标注的是
   20%–100% 规划范围，导致 20% 点没有落在下边界线上。坐标已改为 20%–100%
   映射，并新增上下边界坐标断言；这不改变任何仿真事实或核心实现。

## 可复跑命令与结果

```bash
/workspace/eos-cloud-prep/venv/bin/python -m examples.virtual_home_storage_day.demo \
  --output-dir /tmp/eos-virtual-home-day-final
```

运行成功，生成逐小时 CSV/JSON、关键事件文本、日汇总、联动 SVG，以及既有
reference 输出。教学 SVG 的本地渲染命令：

```bash
inkscape /tmp/eos-virtual-home-day-final/simulated_linked_day_curve.svg \
  --export-type=png \
  --export-filename=/tmp/eos-virtual-home-day-final/simulated_linked_day_curve.png
```

针对性回归：

```bash
/workspace/eos-cloud-prep/venv/bin/python -m pytest \
  tests/integration/test_virtual_home_storage_day.py \
  tests/unit/ems_simulator/test_residential_reference_demo.py \
  tests/integration/test_economic_multi_opportunity_explainable_mpc_daily_simulation.py \
  tests/integration/test_multi_opportunity_explainable_mpc_daily_simulation.py -q
```

结果：`16 passed in 0.60s`。

仓库级静态检查：

```bash
/workspace/eos-cloud-prep/venv/bin/ruff check .
/workspace/eos-cloud-prep/venv/bin/ruff format --check .
/workspace/eos-cloud-prep/venv/bin/mypy .
```

结果：Ruff 全部通过；850 个文件已格式化；Mypy 对 504 个源文件无问题。

全量回归：

```bash
/workspace/eos-cloud-prep/venv/bin/python -m pytest
```

结果：`3008 passed in 419.60s (0:06:59)`。

## 独立验收口径

- 逐小时功率平衡：`PV + grid_signed - battery_signed = load`。
- 充电 SOC：`SOC_after = SOC_before + P_charge × 1h × 0.95 / 10kWh`。
- 放电 SOC：`SOC_after = SOC_before + P_discharge × 1h / 0.95 / 10kWh`，放电功率为负。
- 成本由逐小时购电、出口与吞吐独立积分，不调用教学包装层公式生成 expected。
- 每步核对 `decision → provenance → feasible → handoff → Simulator input/result`
  对象身份，防止以后层事实冒充前层输入。
- 价格声明仅覆盖既有低价电网充电 gate 与事后进口成本核算；不声称该固定日带来
  Schedule/Economic 路径间节省。

## 独立只读复核

全新上下文的 5.6 审查者只读重放候选，结论为 `no findings`：

- 新示例与相关 runner `16 passed`，PR #220 五场景 `18 passed`；
- 独立脚本直接调用既有 runner，复核 24 小时功率、SOC、成本、关键小时、完整
  identity 链、perfect forecast 和 Schedule/Economic 完成结果相同；
- CSV/JSON 对齐且跨进程逐字节确定，SVG 为 6 条各 24 点曲线并可渲染；
- 冻结核心和 PR #220 五场景相对基线均为零差异；
- 未独立重复全量 3008 项测试；主验证已完成该全量门禁。

SOC 轴修复后，同一审查者再次定向复核，结论仍为 `no findings`：新测试
`4 passed`，解析得到 SOC 曲线 `min(y)=390.0`、`max(y)=520.0`，小时 14–17 的
100% 点与小时 21–23 的 20% 点分别贴合上下边界；Inkscape 目视无裁切或错位。
CSV、JSON、关键事件与日汇总相对修复前逐字节不变。
