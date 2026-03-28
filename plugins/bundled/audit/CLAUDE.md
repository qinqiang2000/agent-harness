# Audit Plugin

AI 财务单据审核插件。详细架构见 `README.md`。

## 回归测试

改动 `plugin.py`（标注/OCR/fuzzy match）或 `static/index.html`（报告去重）后，务必跑回归测试：

```bash
source .venv/bin/activate
python -m pytest tests/audit/test_highlight.py -v
```

测试结构：
- `tests/audit/fixtures/highlight_cases.json` — 测试数据（与代码分离，新增场景只需加 JSON）
- `tests/audit/test_highlight.py` — 测试脚本

覆盖范围：
- `TestFuzzyMatch` — `_fuzzy_match()` OCR 文本匹配（防误匹配：数字子串、单字符、日期等）
- `TestHighlightPlacement` — `_find_field_rect()` 在真实 PDF 上的标注位置（覆盖规则 1/3/4/5）
- `TestSearchText` — 图片 PDF 原生文本搜索返回空
- `TestFrontendDedup` — Markdown 报告去重逻辑（JSON 解析后移除逐条详情）

测试 PDF 依赖 `../../audit_demo/报价单.pdf` 和 `收货单.pdf`，缺失时 PDF 相关用例自动 skip。

## 关键修复记录

- **OCR derotation bug**: 旋转 PDF（rotation=270）不应对 OCR 坐标做 derotation，pixmap 已是视觉坐标系
- **fuzzy match 误匹配**: 数字匹配只对纯数字值生效，substring 匹配要求双方长度 >4
- **报告去重**: JSON 解析成功后前端移除 `## 逐条审核结果` 到 `## 审核总结` 之间的内容
