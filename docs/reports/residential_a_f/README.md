# Residential EMS 1.0 A-F 领导汇报

本目录保存四个可直接交付的 **checked-in release snapshots**：21 页技术完整版面向工程、审计与验证复核；12 页领导精简版面向管理层决策。它们是 A-F 冻结控制与报告证据的沟通工件，不是新的控制能力。

## 当前支持

- 四个 checked-in PPTX/PDF release snapshots 可直接交付；
- `tools/verify_residential_a_f_leadership_snapshots.py` 可验证并导出快照；
- 独立的 `tools/generate_residential_leadership_curves.py` 可重建 Campaign A 的曲线 CSV/SVG 证据；
- validator 会检查四个快照的存在性、PPTX/PDF 解析与页数、敏感标记、技术版第 20 页标题及完整 A-F 计数合同；
- validator 将原始快照按字节复制至指定目录，并校验导出 SHA-256 与 tracked snapshots 一致。

## 当前不支持

- 不从零重新生成 21 页或 12 页的完整页面布局；
- 没有独立、完整的 PPT authoring source；
- snapshot validator 不调用 Campaign 曲线生成器；
- snapshot validator 不重新排版 PPT；
- snapshot validator 不生成新的 PDF，只导出 checked-in PDF snapshot。

## Snapshot validation/export

PowerShell 单行命令：

```powershell
python tools/verify_residential_a_f_leadership_snapshots.py --export-dir <output-directory>
```

运行依赖仅为项目 Python 环境与标准库。PowerPoint 或 LibreOffice 仅在人工修改、审阅或重新导出已跟踪快照时需要；它们不是 validator/export 的运行依赖。成功输出为：

```text
PASS snapshot_validation technical=21 executive=12 exported=4
```

缺少、损坏、页数错误、含敏感标记或不满足第 20 页计数合同的快照会非零失败。该入口不会声明 `rebuild complete`、`decks regenerated`、`full report generated` 或其他完整 authoring/rebuild 语义。

## 产物边界

Campaign A-F 已合并代码及 `docs/validation/RESIDENTIAL_VALIDATION_A_F_SUMMARY.md` 是验证事实来源。PPTX/PDF 是冻结后的发布快照，不是 `simulation_output_*` 生成目录。更新报告时必须实际同步所需快照并重新运行 validator；临时 render、probe、调试脚本和中间 CSV/SVG 不提交。

报告是 Residential EMS 1.0 的仿真验证与证据沟通材料，不代表 HIL、PCS/BMS/DSP 实机通信、实机闭环、现场安全认证或客户部署就绪。
