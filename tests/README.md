# 发票云客服 Skill 测试套件

基于 `.claude/skills/customer-service/SKILL.md` 设计的测试套件，用于验证 Agent 客服问答的准确度。

## 文件结构

```
tests/
├── README.md              # 本文件
├── test_questions.py      # 测试问题集定义
├── test_runner.py         # 测试执行器
├── test_evaluator.py      # 人工评估工具
├── test_customer_service_skill.py  # 旧版测试脚本（已弃用）
└── reports/               # 测试报告输出目录
```

## 测试维度

测试用例覆盖以下维度：

| 维度 | 说明 | 用例数 |
|------|------|--------|
| 产品识别 | 能否正确识别产品线（标准版、星瀚、星空等） | 9 |
| 目录定位 | 能否根据问题语义选择正确目录 | 7 |
| 辅助系统 | 乐企、订单系统、RPA通道等 | 5 |
| 多系统协作 | 外部系统对接问题 | 2 |
| 规则遵循 | 标准话术、来源引用等 | 5 |
| 边界情况 | 私有化、API、跨系统等 | 9 |

## 快速开始

### 1. 列出所有测试用例

```bash
source .venv/bin/activate
python tests/test_runner.py --list
```

### 2. 运行所有测试

```bash
python tests/test_runner.py
```

### 3. 运行特定测试

```bash
# 按ID运行
python tests/test_runner.py --id PROD-001

# 按类别运行
python tests/test_runner.py --category 产品识别

# 快速测试（每类别1个）
python tests/test_runner.py --quick
```

### 4. 人工评估

```bash
# 评估测试报告
python tests/test_evaluator.py tests/reports/test_report_xxx.json
```

## 测试用例设计

### 产品识别测试 (PROD-*)

验证能否正确识别用户提及的产品线：

- **PROD-001~003**: 明确产品名称的问题
- **PROD-004~006**: 同义词识别（aws发票云=标准版，星瀚=星瀚旗舰版）
- **PROD-007**: 混淆风险（星空企业版 vs 星空旗舰版）
- **PROD-008~009**: 缺少产品信息，应触发询问

### 目录定位测试 (DIR-*)

验证能否根据问题语义选择正确目录：

- **DIR-001**: 配置类 → `06-构建阶段/产品初始化配置/`
- **DIR-002~003**: 排查类 → `11-常见问题/`
- **DIR-004~005**: 版本类 → `01-交付赋能/产品知识/产品发版说明/`
- **DIR-006~007**: 操作类 → 功能说明手册或一问一答

### 辅助系统测试 (AUX-*)

验证辅助系统相关问题处理：

- **AUX-001~002**: 乐企问题
- **AUX-003~004**: 订单系统（EOP、运营系统同义词）
- **AUX-005**: RPA通道

### 规则遵循测试 (RULE-*)

验证是否遵循 SKILL.md 定义的规则：

- **RULE-001~003**: 标准话术使用场景
- **RULE-004**: 来源引用格式
- **RULE-005**: 产品区分，不混合答案

### 边界情况测试 (EDGE-*, COMP-*)

验证特殊场景处理：

- 多产品比较
- 跨系统协作
- 私有化部署
- API集成
- 领域知识

## 评估标准

### 自动评估

测试执行器会自动检查：

1. **包含检查**: 回答是否包含预期关键词
2. **排除检查**: 回答是否不包含禁止内容
3. **目录检查**: 是否搜索了正确的目录

### 人工评估

使用 `test_evaluator.py` 进行人工评分（1-5分）：

| 维度 | 说明 |
|------|------|
| 产品匹配 | 回答是否针对正确的产品线 |
| 内容准确 | 回答内容是否正确 |
| 来源引用 | 是否正确引用来源 |
| 规则遵循 | 是否遵循标准话术等规则 |
| 完整性 | 是否完整回答了问题 |

## 添加新测试用例

在 `test_questions.py` 中添加新的 `TestCase`:

```python
TestCase(
    id="PROD-010",                    # 唯一ID
    name="新测试用例名称",              # 测试名称
    category=TestCategory.PRODUCT_RECOGNITION,  # 类别
    query="用户问题",                  # 测试输入
    expected_behaviors=[              # 预期行为（用于人工参考）
        "识别产品线：xxx",
        "搜索xxx目录",
    ],
    expected_product="产品名",         # 可选：预期产品
    expected_directory="目录路径/",    # 可选：预期搜索目录
    expected_output_contains=["关键词"],      # 可选：回答必须包含
    expected_output_not_contains=["禁止词"],  # 可选：回答不应包含
    notes="备注"                       # 可选：备注
)
```

## 测试报告

测试完成后会在 `tests/reports/` 生成 JSON 格式报告：

```json
{
  "generated_at": "2024-01-01T12:00:00",
  "summary": {
    "total": 37,
    "passed": 35,
    "failed": 2,
    "errors": 0
  },
  "results": [...]
}
```

## 常见问题

### Q: 测试运行很慢？

每个测试用例需要调用 Agent 进行问答，平均耗时约 10-30 秒。使用 `--quick` 参数可以快速验证。

### Q: 如何只测试新加的用例？

```bash
python tests/test_runner.py --id YOUR-NEW-ID
```

### Q: 测试结果如何持久化？

每次运行会自动保存报告到 `tests/reports/`，文件名包含时间戳。
