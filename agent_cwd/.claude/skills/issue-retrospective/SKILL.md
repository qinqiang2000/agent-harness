# issue-retrospective

## 角色
批量复盘 Agent，每天凌晨对当天所有已完成的 Linear issue 进行复盘分析，识别 Agent 诊断错误的根因，生成知识库改进草稿，并通过云之家通知负责人 review。

## 触发方式
由 APScheduler 定时触发（每天凌晨 2:00），不对用户直接暴露。

## 执行步骤

### Step 1：收集当天 issue 数据
读取 `log/interactions.log`，筛选当天的诊断类 session（skill 为 issue-diagnosis-billing 或 issue-diagnosis）。
对每个 session 判断是否存在以下纠正信号：
- 用户回复了"2 未解决"
- 用户在对话中出现明显纠正（包含"不是"、"不对"、"应该是"、"实际上"等关键词）
- 同一 issue 出现 3 轮以上对话才收敛

### Step 2：跨 issue 聚合分析
对筛选出的有问题 session，分析错误类型：
- **知识缺失**：Agent 不了解业务规则/表结构语义，导致误判
- **推理路径偏差**：业务知识足够但推理方向走错
- **服务定位错误**：找错了服务或文件

对同类错误进行合并（同一知识点缺失触发多个 issue 只生成一条草稿）。

### Step 3：生成改进草稿
在 `agent_cwd/.claude/skills/issue-retrospective/pending/` 下生成草稿文件，文件名格式：`{日期}_{错误类型}_{issueId}.md`。

草稿格式见下方模板。

### Step 4：云之家通知
调用云之家通知接口，发送消息给管理员 openid，内容包含：
- 今日复盘完成，共分析 X 个 issue
- 有 Y 条知识草稿待 review
- 文件路径列表

## 草稿文件格式模板

```markdown
# {issueId} 复盘 - {日期}

## 错误类型
{知识缺失 / 推理路径偏差 / 服务定位错误}

## 涉及 issue
- {issueId}：{issue 标题}

## 根因描述
{Agent 在哪一步出错，为什么出错}

## 用户纠正内容
{用户的原话}

## 建议写入知识库

**目标文件**：{references/ 下的具体文件名}

**新增内容**：
{具体的知识条目内容}

## 操作
- [ ] 确认写入知识库
- [ ] 拒绝（在此说明原因）
```

## 注意事项
- 只生成草稿，不自动修改知识库文件
- SKILL.md 修改建议也只输出 diff，不自动修改
- 同一知识点多个 issue 触发时合并为一条草稿
