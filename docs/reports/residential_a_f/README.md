# Residential EMS 1.0 A-F 领导汇报

本目录保存两套可直接交付的发布快照，并将其与可复现的曲线证据源放在同一正式报告边界内：21 页技术完整版面向工程、审计和验证复核；12 页领导精简版面向管理层决策。

## Source of truth

- `tools/build_residential_a_f_leadership_reports.py` 是正式构建入口；
- Campaign A-F 已合并代码和 `docs/validation/RESIDENTIAL_VALIDATION_A_F_SUMMARY.md` 是验证事实来源；
- 曲线使用冻结 Campaign A runner 的 Simulator actual state；
- PPTX/PDF 是 checked-in release snapshots，而非 `simulation_output_*` 证据目录。

## 构建

PowerShell 单行命令：

```powershell
python tools/build_residential_a_f_leadership_reports.py --output-dir docs/reports/residential_a_f
```

构建器要求 Python 3.14+、Node.js（含 `@oai/artifact-tool`）及 Microsoft PowerPoint（用于非交互式 PDF 导出）。缺少任一依赖会明确失败；不会把旧 PDF 当作成功产物。构建会验证技术版 21 页、精简版 12 页、四个文件存在、关键标题/计数以及敏感路径标记。

## 产物策略

四个 PPTX/PDF 是发布快照，便于领导直接获取；生成器和冻结 Campaign 证据提供可重建来源。临时 render、probe、调试脚本和中间 CSV/SVG 不提交。更新报告时必须同时更新四个快照并验证页数与同步性。不同 PowerPoint/PDF producer 的元数据可能不同，因此可重建性以页面数、解析文本、曲线内容和渲染结果一致为准，不承诺二进制逐字节相同。

## 能力边界

报告是冻结 Residential EMS 1.0 的仿真验证与证据沟通材料，不代表 HIL、PCS/BMS/DSP 实机通信、实机闭环、现场安全认证或客户部署就绪。
