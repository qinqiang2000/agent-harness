---
name: regression-test
description: 运行回归测试并评分，对比历史 baseline，验证代码改动没有引入回归问题。当用户说"跑回归测试"、"评分"、"和baseline对比"、"验证改动"时使用。
---

# 回归测试 Skill

## 测试集说明

| 测试集 | 文件 | 题数 | 用途 | 对应 baseline |
|--------|------|------|------|--------------|
| test_set_0 | tests/dataset/test_set_0.md | 56题 | 早期人工挑选的难题集（独立测试） | baseline_v5.scored.json |
| test_set_1 | tests/dataset/test_set_1.md | 49题 | 早期补充难题集 | （无 baseline） |
| test_set_faq | tests/dataset/test_set_faq.md | 553题 | 真实 FAQ 全量回归（含 631 条 golden_set_faq.json） | baseline_feishu_grep.scored.json |

**选择建议：**
- 验证语雀 customer-service skill 改动 → 用 **test_set_0**（baseline_v5 是该 skill 历史最佳）
- 验证飞书 customer-service-feishu skill 改动 → 用 **test_set_faq**（baseline_feishu_grep 含 631 条标准答案）
- 快速验证（成本低）→ 用 test_set_0（56题，约 30-50 分钟）
- 全量验证 → 用 test_set_faq（553题，约 4-6 小时）

---

## Step 1：运行批量测试

```bash
cd /Users/leiquanchun/code/agent-harness

# 使用 test_set_0（语雀 skill 回归，56题）
source .venv/bin/activate && python tests/batch_test.py tests/dataset/test_set_0.md \
    --skill customer-service --default-product "星瀚旗舰版" --concurrency 2 2>&1 | tail -20

# 使用 test_set_faq（飞书 skill 回归，553题）
source .venv/bin/activate && python tests/batch_test.py tests/dataset/test_set_faq.md \
    --skill customer-service-feishu --concurrency 2 2>&1 | tail -20
```

记录输出中的结果文件路径（格式：`tests/results/test_set_X_YYYYMMDD_HHMMSS.json`）。

---

## Step 2：对结果打分

```bash
source .venv/bin/activate && python tests/score_results.py tests/results/<上一步的文件名>.json
```

打分完成后生成 `*.scored.json`。`score_results.py` 会自动按文件名匹配对应的 golden_set（test_set_faq → golden_set_faq.json，其他 → golden_set.jsonl）。

---

## Step 3：对比 baseline

```bash
# test_set_0 对比 baseline_v5
python tests/compare_runs.py tests/results/baseline_v5.scored.json tests/results/<新.scored.json>

# test_set_faq 对比 baseline_feishu_grep
python tests/compare_runs.py tests/results/baseline_feishu_grep.scored.json tests/results/<新.scored.json>
```

`compare_runs.py` 会输出综合分、各维度变化、Bad case 数、响应时间对比，并给出 ACCEPT/REJECT/REVIEW 决策建议。


## Step 4：输出结论

根据对比结果给出结论：

- 平均分下降 > 0.5 或 bad case 率上升 > 5%：**存在回归风险**，列出具体 bad case 题目
- 平均分变化在 ±0.5 以内且 bad case 率变化在 ±5% 以内：**无回归**
- 平均分上升：**有改善**

---

## Step 5（可选）：保存新 baseline

如果本次结果良好，询问用户是否保存为新 baseline：

```bash
python3 - <<'EOF'
import re
from pathlib import Path

files = sorted(Path("tests/results").glob("baseline_v*.scored.json"))
latest_v = max(int(re.search(r'v(\d+)', f.name).group(1)) for f in files) if files else 0
next_v = latest_v + 1

# 取最新 scored 结果
new_path = sorted(Path("tests/results").glob("test_set_*.scored.json"))[-1]
dest = Path(f"tests/results/baseline_v{next_v}.scored.json")

import shutil
shutil.copy(new_path, dest)
print(f"已保存为 {dest.name}")
EOF
```
