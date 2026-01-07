# Claude Code CLI 多轮对话 Demo 使用说明

## 功能特性

### 1. 多轮对话支持
- 自动保存和复用 `session_id`
- 支持会话重置和查看
- 使用 Claude Code CLI 的 `--resume` 功能

### 2. 流式输出（默认开启）
- 使用 `--output-format stream-json` 实时显示 Claude 的回复
- 像 `tail -f` 一样实时查看输出，无需等待完整响应
- 支持实时显示工具调用、待办事项更新等事件
- Verbose 模式下显示所有事件类型

### 3. 详细的响应解析

根据 Claude CLI 的 `--output-format json` 实际返回格式，提供详细的信息展示：

#### 基础信息
- **Claude 回复内容**：主要的文本响应
- **会话 ID**：简短版本和完整 UUID

#### 性能指标
- **总耗时**（duration_ms）：整个请求的总时间
- **API 耗时**（duration_api_ms）：实际 API 调用时间
- **轮次数**（num_turns）：对话轮次

#### 成本统计
- **总成本**（total_cost_usd）：请求的总成本（USD）

#### Token 使用详情
- **输入 tokens**：用户输入消耗的 tokens
- **输出 tokens**：Claude 回复消耗的 tokens
- **缓存创建**：创建提示缓存消耗的 tokens
- **缓存读取**：从缓存读取节省的 tokens（降低成本）
- **总计**：所有 tokens 的总和
- **工具调用统计**：Web Search、Web Fetch 等工具的调用次数

#### 模型使用详情
- 按模型统计的详细信息
- 上下文窗口大小
- 每个模型的成本

#### 其他功能
- **权限拒绝记录**：显示被拒绝的权限请求
- **待办事项**：如果 Claude 使用了 TodoWrite 工具，显示待办列表
- **错误状态**：明确标识请求是否发生错误

### 4. Verbose 模式

使用 `--verbose` 参数可以：
- 在流式模式下显示所有事件类型（工具调用、待办事项更新等）
- 在批量模式下显示完整的原始 JSON 响应

## 使用方法

### 基础使用（推荐）

默认启用流式输出和自动权限批准：

```bash
python claude_cli_demo.py
```

### 使用代理

有两种方式设置代理：

**方式 1：通过命令行参数（推荐）**

```bash
python claude_cli_demo.py --proxy http://127.0.0.1:7890
```

这会自动设置 `http_proxy`、`https_proxy` 和 `all_proxy` 环境变量给 `claude` 命令。

**方式 2：继承 Shell 环境变量**

如果你已经在 Shell 中设置了代理环境变量：

```bash
export https_proxy=http://127.0.0.1:7890
export http_proxy=http://127.0.0.1:7890
export all_proxy=socks5://127.0.0.1:7890

python claude_cli_demo.py
```

程序会自动继承这些环境变量，无需再指定 `--proxy` 参数。

### 指定工作目录

```bash
python claude_cli_demo.py --cwd /path/to/project
```

### 自定义允许的工具

```bash
python claude_cli_demo.py --tools "Read,Grep,Bash"
```

### 显示详细日志（Verbose 模式）

在流式模式下显示所有事件：

```bash
python claude_cli_demo.py --verbose
```

### 使用批量模式（非流式）

如果不想要实时输出，可以禁用流式：

```bash
python claude_cli_demo.py --no-stream
```

### 要求权限确认

如果需要手动确认每个工具调用：

```bash
python claude_cli_demo.py --no-skip-permissions
```

### 组合使用

```bash
# 批量模式 + 详细日志
python claude_cli_demo.py --no-stream --verbose

# 指定工作目录 + 详细日志
python claude_cli_demo.py --cwd /path/to/project --verbose
```

## 交互式命令

在 REPL 模式下，支持以下命令：

- **输入问题**：直接输入问题开始或继续对话
- **`exit` 或 `quit`**：退出程序
- **`reset`**：重置会话，开始新对话
- **`session`**：查看当前会话 ID

## 示例输出

### 流式模式（默认）

实时显示 Claude 的回复，像 `tail -f` 一样：

```
[执行命令] claude -p "2+2等于几" --output-format stream-json --allowedTools Read,Grep,Glob,Bash,WebFetch --dangerously-skip-permissions
--------------------------------------------------------------------------------
🔄 实时流式输出:

✅ 会话已创建: c82e0eea...

2 + 2 = 4。

--------------------------------------------------------------------------------
📝 会话ID: c82e0eea... (完整: c82e0eea-a45d-4927-b9a7-89059033e535)
⏱️  总耗时: 4.12s | API耗时: 3.98s | 🔄 轮次: 1
💰 成本: $0.000456 USD
📊 Token: 输入 3 | 输出 14 | 缓存读取 12,834
================================================================================
```

### 流式 + Verbose 模式

显示所有事件（工具调用、待办事项等）：

```
🔄 实时流式输出:

✅ 会话已创建: c82e0eea...

[🔧 工具调用: Read]
[事件: tool_use]

根据文件内容，这是一个...

[📋 待办事项更新: 3 项]
[事件: todos_update]

... （实时输出的文本）
```

### 批量模式（`--no-stream`）

等待完整响应后一次性显示：

```
🤖 Claude 回复:

2 + 2 = 4。

--------------------------------------------------------------------------------
📝 会话ID: c82e0eea... (完整: c82e0eea-a45d-4927-b9a7-89059033e535)
⏱️  总耗时: 98.86s | API耗时: 4.02s | 🔄 轮次: 1
💰 成本: $0.045604 USD
📊 Token 使用:
   • 输入: 3 tokens
   • 输出: 14 tokens
   💾 缓存:
      - 创建: 11,076 tokens
      - 读取: 12,834 tokens (节省成本)
   🔢 总计: 23,927 tokens

📋 模型使用详情:
   • sonnet-4-5-20250929
     - 上下文窗口: 200,000 tokens
     - 成本: $0.045604 USD

================================================================================
```

### 批量 + Verbose 模式

先显示完整的原始 JSON 响应，然后显示格式化输出：

```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "duration_ms": 98858,
  "duration_api_ms": 4016,
  "num_turns": 1,
  "result": "2 + 2 = 4。",
  "session_id": "c82e0eea-a45d-4927-b9a7-89059033e535",
  ...
}
```
（然后是格式化的输出）

## 测试

运行测试脚本查看响应解析效果：

```bash
python test_cli_demo.py
```

该脚本会演示：
1. 普通模式的响应解析
2. Verbose 模式的原始 JSON 显示

## 技术细节

### JSON 响应格式

Claude CLI 的 `--output-format json` 返回的 JSON 包含以下主要字段：

- `type`: 消息类型（如 "result"）
- `subtype`: 子类型（如 "success"）
- `is_error`: 是否发生错误
- `result`: 最终的文本响应
- `session_id`: 会话 ID
- `duration_ms`: 总耗时（毫秒）
- `duration_api_ms`: API 调用耗时（毫秒）
- `num_turns`: 对话轮次
- `total_cost_usd`: 总成本（美元）
- `usage`: Token 使用详情
  - `input_tokens`: 输入 tokens
  - `output_tokens`: 输出 tokens
  - `cache_creation_input_tokens`: 缓存创建 tokens
  - `cache_read_input_tokens`: 缓存读取 tokens
  - `server_tool_use`: 服务端工具使用统计
- `modelUsage`: 按模型的使用详情
- `permission_denials`: 权限拒绝列表
- `uuid`: 请求唯一标识符

### 代理设置

如果遇到网络连接问题，可以在执行前设置代理：

```bash
export https_proxy=http://127.0.0.1:7890
export http_proxy=http://127.0.0.1:7890
export all_proxy=socks5://127.0.0.1:7890
```

## 常见问题

### Q: 如何查看当前会话 ID？
A: 在 REPL 中输入 `session` 命令。

### Q: 如何开始一个新对话？
A: 在 REPL 中输入 `reset` 命令，或者重启程序。

### Q: 如何理解缓存相关的 tokens？
A:
- **cache_creation_input_tokens**: 创建提示缓存消耗的 tokens（首次请求）
- **cache_read_input_tokens**: 从缓存读取的 tokens（后续请求，成本更低）
- 缓存可以显著降低多轮对话的成本

### Q: 为什么 API 耗时比总耗时短很多？
A: 总耗时包括网络传输、本地处理、工具调用等时间，API 耗时仅指实际的模型推理时间。

## 许可证

本项目与主项目共享许可证。
