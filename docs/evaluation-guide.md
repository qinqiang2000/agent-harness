# 发票云客服 Agent 评测使用手册

## 概述

这套评测框架用于衡量客服 Agent 的回答质量，帮助你判断对 Agent 的调整是否真正有效。

核心思路：**先跑测试建立基准，改完再跑一次，对比两次结果。**

---

## 文件说明

```
tests/
├── batch_test.py              # 批量跑问题，收集 Agent 回答
├── score_results.py           # 对回答打分
├── compare_runs.py            # 对比两次结果，给出建议
├── qa/
│   └── qa_questions.md        # 测试问题集（32条）
├── dataset/
│   └── golden_set.jsonl       # 每道题的行为期望
└── results/
    ├── baseline_v3.scored.json  # 当前基准（7.67分）
    └── ...                      # 历次测试结果
```

---

## 快速上手

### 第一步：跑一次测试

```bash
cd /Users/leiquanchun/code/agent-harness
source .venv/bin/activate

python tests/batch_test.py tests/qa/qa_questions.md --concurrency 3 --timeout 360
```

等待约 15-20 分钟，完成后在 `tests/results/` 下生成一个 JSON 文件。

### 第二步：打分

```bash
python tests/score_results.py tests/results/qa_questions_XXXXXXXX_XXXXXX.json
```

### 第三步：和基准对比

```bash
python tests/compare_runs.py tests/results/baseline_v3.scored.json \
                              tests/results/qa_questions_XXXXXXXX_XXXXXX.scored.json
```

---

## 如何读懂评分结果

### 总体指标

| 指标 | 含义 | 当前基准 |
|------|------|---------|
| 平均分 | 综合质量，满分 10 分 | 7.67 |
| Bad cases | 低于 6 分的题目数 | 7/32 |
| 行为验证通过率 | 确定性行为检查通过比例 | 88% |

### 评分维度

| 维度 | 满分 | 含义 |
|------|------|------|
| 产品识别 | 3 | 是否正确识别了用户使用的产品 |
| KB依据 | 3 | 回答是否引用了知识库链接 |
| 答案准确性 | 3 | 内容是否正确 |
| 输出格式 | 3 | 结论是否前置、是否简洁、有无内部过程泄漏 |
| 兜底处理 | 3 | 知识库无答案时是否正确兜底 |

### 行为验证

行为验证是**确定性检查**，不依赖 AI 打分，结果稳定可靠。

检查两件事：
- **产品消歧**：Agent 是否在该问的时候问了产品，不该问的时候没有问
- **兜底话术**：Agent 是否在知识库无答案时输出了标准兜底话术

**行为验证失败会强制将该题分数压到 4.0 分以下**，无论回答内容多好。

### 对比结果的决策规则

```
✅ ACCEPT — 综合分提升 ≥ 0.5 且 bad cases 不增加
❌ REJECT — 行为验证通过率下降 > 5%（硬性回退）
⚠️ REVIEW — 变化不显著，需人工确认
```

---

## 测试集维护

### 测试集的三层数据

```
qa_questions.md      — 问什么（问题本身）
golden_set.jsonl     — 怎么做（行为期望）
gold_doc_url/key_facts — 说什么（答案期望，目前待填充）
```

**测试集是评测框架的地基，比 SKILL.md 本身更重要。**

### 什么时候需要更新测试集

| 业务变化 | 需要更新的地方 |
|---------|--------------|
| 新增产品线 | qa_questions.md 补问题，golden_set.jsonl 补期望 |
| 修改产品消歧规则 | golden_set.jsonl 中相关题目的 `expected_product_ask` |
| 修改兜底触发条件 | golden_set.jsonl 中相关题目的 `expected_fallback` |
| 新增知识库内容 | 原来兜底的题目可能要改为 `expected_fallback: false` |
| 修改兜底话术文本 | `api/utils/interaction_logger.py` 中的 `FALLBACK_PHRASE` |

> ⚠️ **重要原则**：先改 golden_set，再改 SKILL.md，再跑测试。顺序反了会导致"期望降低了但误以为 Agent 变好了"。

### golden_set.jsonl 字段说明

每条记录的格式：

```json
{
  "id": "qs-001",
  "question": "发票云支持批量开票吗？",
  "category": "售后操作",
  "expected_product_ask": true,
  "expected_fallback": false,
  "gold_doc_url": null,
  "key_facts": [],
  "must_not_contain": []
}
```

| 字段 | 说明 |
|------|------|
| `expected_product_ask` | true = Agent 应该先问用户用的是哪款产品 |
| `expected_fallback` | true = Agent 应该输出兜底话术（知识库无答案） |
| `gold_doc_url` | 标准答案所在的知识库文档 URL（填了之后评分更准确） |
| `key_facts` | 答案必须包含的关键事实点 |
| `must_not_contain` | 答案不能包含的内容（防止错误信息） |

### expected_product_ask 判断原则

**应该设为 true（需要问产品）：**
- 问题涉及具体功能配置，但没有明确产品名（如"激活码在哪里"）
- 问题包含歧义词："旗舰版"（星瀚 vs 星空）、"星空企业版"、"企业版"

**应该设为 false（不需要问产品）：**
- 问题已明确产品（如"星瀚旗舰版如何..."）
- 税务政策、开票规范等通用问题
- 售前通用咨询：私有化部署能力、第三方集成能力（能否集成）、产品选型
- 竞品价格对比、优惠套餐（这类直接兜底，不需要问产品）

### expected_fallback 判断原则

**应该设为 true（应该兜底）：**
- 知识库里确实没有相关内容（用 `qmd search <问题>` 验证）
- 竞品价格对比、优惠折扣等商业敏感信息

**应该设为 false（应该给出答案）：**
- 知识库里有相关文档，Agent 能搜到

> 验证方法：在项目目录下运行 `qmd search "你的问题关键词"` 确认知识库是否有内容。

---

## 历史基准

| 版本 | 文件 | 平均分 | Bad cases | 行为验证 | 主要变化 |
|------|------|--------|-----------|---------|---------|
| v1 | baseline_v1.scored.json | 6.48 | 13/32 | 63% | 初始基准 |
| v2 | baseline_v2.scored.json | 7.32 | 8/32 | 84% | 修复产品消歧规则 |
| v3 | baseline_v3.scored.json | 7.67 | 7/32 | 88% | 修复兜底话术检测 |

---

## 常见问题

**Q：行为验证通过了但分数还是很低？**

说明 Agent 行为正确（问了该问的，兜底了该兜底的），但回答内容质量有问题。看 `accuracy` 和 `kb_grounded` 维度，可能是搜到了错误文档或答案不准确。

**Q：分数波动很大，同一道题不同次结果差很多？**

LLM judge 有 ±0.5 分的随机性，属于正常现象。单题分数波动不可信，看整体平均分和 bad cases 数量的趋势。

**Q：改了 SKILL.md 但分数反而下降了？**

先看行为验证回退列表，找出哪些题目从通过变成了失败。通常是新加的规则范围太宽，误伤了原本正确的问题。回滚该修改，缩小规则范围后重试。

**Q：想验证某一条具体问题的效果？**

在 `qa_questions.md` 里只保留那一条问题，跑 batch_test.py，看 Agent 的实际回答。
