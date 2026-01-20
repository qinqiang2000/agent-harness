# PRD Generator Skill

PRD生成Agent，负责根据用户需求生成结构化的产品需求文档（Product Requirements Document）。

## 功能特性

- 基于《业务动作表》和《数据标准字典》知识库生成符合发票云业务规范的PRD文档
- **支持读取 Excel 格式的数据标准字典**
- 提供结构化的 PRD 模板
- 智能信息收集和补全

## 知识库资源

1. **《业务动作表》V2.md** - 9个核心开票功能的完整业务动作定义
2. **《数据标准字典-销项发票数据》V0.1.xlsx** - 销项发票相关的数据模型和字段规范

## 安装依赖

```bash
# 进入项目根目录
cd agent-harness

# 激活虚拟环境
source .venv/bin/activate

# 安装依赖（包含 openpyxl）
pip install -r requirements.txt
```

## Excel 读取工具使用

### 基本用法

```bash
# 进入 prd-generator skill 目录
cd .claude/skills/prd-generator

# 读取 Excel 文件（Markdown 格式）
python scripts/excel_reader.py reference/01-《数据标准字典-销项发票数据》V0.1.xlsx

# 指定输出格式
python scripts/excel_reader.py reference/01-《数据标准字典-销项发票数据》V0.1.xlsx markdown
python scripts/excel_reader.py reference/01-《数据标准字典-销项发票数据》V0.1.xlsx json
python scripts/excel_reader.py reference/01-《数据标准字典-销项发票数据》V0.1.xlsx text
```

### 输出格式说明

- **markdown**（推荐）：生成 Markdown 表格，便于阅读和在文档中引用
- **json**：生成 JSON 格式，便于程序处理
- **text**：生成纯文本，使用 Tab 分隔

### 测试脚本

```bash
# 运行测试脚本验证 Excel 读取功能
python scripts/test_excel_reader.py
```

## Agent 使用示例

### 触发词

PRD、产品需求文档、需求文档、功能设计、用户故事、需求分析

### 使用场景

1. **新功能开发**
   ```
   我想开发一个批量开具数电发票的功能
   ```

2. **功能优化**
   ```
   现有的发票打印功能需要支持批量打印
   ```

3. **基于用户故事**
   ```
   作为财务人员，我希望能够批量导出发票数据，以便进行财务对账
   ```

## 技术实现

### Excel 读取原理

使用 `openpyxl` 库读取 Excel 文件：
- 支持 `.xlsx` 格式
- 自动识别所有工作表
- 提取表头和数据行
- 转换为 Markdown/JSON/Text 格式

### Agent 工作流程

1. **需求理解** - 识别需求类型和关键信息
2. **知识库匹配** - 查询业务动作表和数据标准字典
3. **Excel 读取** - 使用 `excel_reader.py` 读取数据字典（如需要）
4. **信息补全** - 使用 AskUserQuestion 工具收集必要信息
5. **文档生成** - 按照标准模板生成完整 PRD
6. **质量检查** - 验证需求描述的清晰性和完整性

## 故障排查

### 问题：无法读取 Excel 文件

**解决方案**：
```bash
# 检查 openpyxl 是否已安装
pip list | grep openpyxl

# 如未安装，手动安装
pip install openpyxl
```

### 问题：文件路径错误

**解决方案**：
- 确保 Excel 文件在 `reference/` 目录下
- 使用相对路径：`reference/01-《数据标准字典-销项发票数据》V0.1.xlsx`

### 问题：中文乱码

**解决方案**：
- 脚本已使用 `ensure_ascii=False` 处理中文
- 确保终端支持 UTF-8 编码

## 更多信息

详细的 Skill 定义和执行规则请参考 [SKILL.md](SKILL.md)
