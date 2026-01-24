# CLAUDE.md

该文件为 Claude Code 提供本项目的操作指南。

## 项目简介

基于 FastAPI + Claude Agent SDK 的 AI Agent 服务，支持 Skill 扩展。

## 开发命令

```bash
# 启动服务（带自动重载）
./run.sh start

# 停止服务
./run.sh stop

# 重启（默认）
./run.sh
```

## Skill 系统

Skills 位于 `agent_cwd/.claude/skills/`，详见各技能的 SKILL.md。

## 关键路径

- `AGENT_CWD` 环境变量指定 Agent 工作目录（默认 `agent_cwd/`）
- Skills: `agent_cwd/.claude/skills/`
- 知识库: `agent_cwd/data/kb/`

## 注意事项

- Skill 输出最终结果：直接输出内容
- Skill 询问用户：必须使用 `AskUserQuestion` 工具
