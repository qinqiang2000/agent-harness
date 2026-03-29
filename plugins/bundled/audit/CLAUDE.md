# Audit Plugin

AI 财务单据审核插件。详细架构见 `README.md`。

## 回归测试

改动后务必跑全部回归测试：

```bash
source .venv/bin/activate
python -m pytest tests/audit/ -v
```

测试文件：
- `tests/audit/test_highlight.py` — PDF 标注核心函数测试
- `tests/audit/test_multi_rule.py` — 多规则比对功能验收测试
- `tests/audit/fixtures/highlight_cases.json` — 标注测试数据
- `tests/audit/fixtures/multi_rule_cases.json` — 多规则测试数据

覆盖范围：
- `TestFuzzyMatch` — `_fuzzy_match()` OCR 文本匹配（防误匹配：数字子串、单字符、日期等）
- `TestHighlightPlacement` — `_find_field_rect()` 在真实 PDF 上的标注位置（覆盖规则 1/3/4/5）
- `TestSearchText` — 图片 PDF 原生文本搜索返回空
- `TestCategoryGrouping` — 规则按 category 分组逻辑
- `TestPromptBuilding` — handler prompt 包含 rule ID
- `TestStatusFilter` — 审核结果按状态筛选
- `TestBatchPanelGeneration` — 白板批量面板生成与合并
- `TestMultiRuleJsonParse` — 多规则 JSON 解析与去重
- `TestRuleColors` — 规则颜色唯一性

测试 PDF 依赖 `../../audit_demo/报价单.pdf` 和 `收货单.pdf`，缺失时 PDF 相关用例自动 skip。

## 关键修复记录

- **OCR derotation bug**: 旋转 PDF（rotation=270）不应对 OCR 坐标做 derotation，pixmap 已是视觉坐标系
- **fuzzy match 误匹配**: 数字匹配只对纯数字值生效，substring 匹配要求双方长度 >4
- **报告去重**: JSON 解析成功后前端移除 `## 逐条审核结果` 到 `## 审核总结` 之间的内容
