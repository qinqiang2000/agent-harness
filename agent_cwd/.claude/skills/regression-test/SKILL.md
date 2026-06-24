---
name: regression-test
description: 运行回归测试并评分，对比历史 baseline，验证代码改动没有引入回归问题。当用户说"跑回归测试"、"评分"、"和baseline对比"、"验证改动"时使用。
---

# 回归测试 Skill

## 测试集说明

| 测试集 | 文件 | 题数 | 对应 baseline |
|--------|------|------|--------------|
| test_set_0 | tests/dataset/test_set_0.md | 56题 | baseline_v4.scored.json |
| test_set_1 | tests/dataset/test_set_1.md | 49题 | baseline_v5.scored.json（待建立） |

默认使用 **test_set_0**（有历史 baseline 可对比）。

---

## Step 1：运行批量测试

```bash
cd /Users/leiquanchun/code/agent-harness

# 使用 test_set_0（默认，有 baseline 可对比）
source .venv/bin/activate && python tests/batch_test.py tests/dataset/test_set_0.md --default-product "星瀚旗舰版" 2>&1 | tail -20

# 或使用 test_set_1
source .venv/bin/activate && python tests/batch_test.py tests/dataset/test_set_1.md --default-product "星瀚旗舰版" 2>&1 | tail -20
```

记录输出中的结果文件路径（格式：`tests/results/test_set_X_YYYYMMDD_HHMMSS.json`）。

---

## Step 2：对结果打分

```bash
source .venv/bin/activate && python tests/score_results.py tests/results/<上一步的文件名>.json
```

打分完成后生成 `*.scored.json`。

---

## Step 3：对比 baseline

```bash
python3 - <<'EOF'
import json
from pathlib import Path

def load(path):
    with open(path) as f:
        return json.load(f)

# 根据测试集选择对应 baseline
# test_set_0 → baseline_v4
# test_set_1 → baseline_v5（如已建立）
baseline_path = Path("tests/results/baseline_v4.scored.json")

# 取最新的 scored 结果
new_path = sorted(Path("tests/results").glob("test_set_*.scored.json"))[-1]

b = load(baseline_path)
n = load(new_path)
bm = b["_meta"]
nm = n["_meta"]

print(f"{'指标':<20} {'baseline':>12} {'本次':>12} {'变化':>10}")
print("-" * 56)

avg_b = bm.get("avg_quality_score", 0)
avg_n = nm.get("avg_quality_score", 0)
print(f"{'平均分':<20} {avg_b:>12.2f} {avg_n:>12.2f} {avg_n-avg_b:>+10.2f}")

bad_b = bm.get("bad_case_count", 0)
bad_n = nm.get("bad_case_count", 0)
total_b = bm.get("total", 1)
total_n = nm.get("total", 1)
print(f"{'Bad case 数':<20} {bad_b:>12} {bad_n:>12} {bad_n-bad_b:>+10}")
print(f"{'Bad case 率':<20} {bad_b/total_b*100:>11.1f}% {bad_n/total_n*100:>11.1f}% {(bad_n/total_n-bad_b/total_b)*100:>+9.1f}%")

# 维度对比
dims = ["product_id", "kb_grounded", "accuracy", "format", "missing_handling"]
b_results = [r for r in b["results"] if r.get("scores")]
n_results = [r for r in n["results"] if r.get("scores")]
if b_results and n_results:
    print(f"\n{'维度':<20} {'baseline':>12} {'本次':>12} {'变化':>10}")
    print("-" * 56)
    for dim in dims:
        b_scores = [r["scores"].get(dim, -1) for r in b_results]
        n_scores = [r["scores"].get(dim, -1) for r in n_results]
        b_valid = [s for s in b_scores if s >= 0]
        n_valid = [s for s in n_scores if s >= 0]
        if b_valid and n_valid:
            avg_b_dim = sum(b_valid) / len(b_valid)
            avg_n_dim = sum(n_valid) / len(n_valid)
            print(f"  {dim:<18} {avg_b_dim:>12.2f} {avg_n_dim:>12.2f} {avg_n_dim-avg_b_dim:>+10.2f}")

print(f"\nbaseline: {baseline_path.name}")
print(f"本次:     {new_path.name}")
EOF
```

---

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
