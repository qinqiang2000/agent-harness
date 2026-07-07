#!/usr/bin/env bash
# setup_knowledge.sh
# 初始化外部知识库依赖（星瀚 Product-Wiki 等）
#
# 用法：
#   ./scripts/setup_knowledge.sh
#
# 环境变量（可在 .env 中配置）：
#   KNOWLEDGE_BASE_DIR  知识库 clone 根目录（默认 ~/code/github-master）
#   XINGHAN_WIKI_REPO   Product-Wiki 仓库地址

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 加载 .env（如果存在）
if [[ -f "$PROJECT_ROOT/.env" ]]; then
  set -a
  source "$PROJECT_ROOT/.env"
  set +a
fi

KNOWLEDGE_BASE_DIR="${KNOWLEDGE_BASE_DIR:-$HOME/code/github-master}"
XINGHAN_WIKI_REPO="${XINGHAN_WIKI_REPO:-}"
AGENT_CWD="${AGENT_CWD:-agent_cwd}"
AGENT_CWD_ABS="$PROJECT_ROOT/$AGENT_CWD"

# ── Product-Wiki ───────────────────────────────────────────────────────────────
if [[ -z "$XINGHAN_WIKI_REPO" ]]; then
  echo "⚠️  XINGHAN_WIKI_REPO 未配置，跳过 Product-Wiki 初始化"
  echo "   请在 .env 中设置 XINGHAN_WIKI_REPO=git@github.com:your-org/Product-Wiki.git"
else
  WIKI_DIR="$KNOWLEDGE_BASE_DIR/Product-Wiki"
  mkdir -p "$KNOWLEDGE_BASE_DIR"

  if [[ -d "$WIKI_DIR/.git" ]]; then
    echo "▶ Product-Wiki 已存在，拉取最新..."
    git -C "$WIKI_DIR" pull --quiet
    echo "  ✅ 已更新: $WIKI_DIR"
  else
    echo "▶ 克隆 Product-Wiki..."
    git clone "$XINGHAN_WIKI_REPO" "$WIKI_DIR"
    echo "  ✅ 已克隆: $WIKI_DIR"
  fi

  # 直接同步到 data/Product-Wiki（不用软链，Claude glob 无法穿透软链）
  DEST_DIR="$AGENT_CWD_ABS/data/Product-Wiki"
  # 如果目标是软链先删除，避免 rsync 写入原始目录
  if [[ -L "$DEST_DIR" ]]; then
    rm "$DEST_DIR"
  fi
  mkdir -p "$DEST_DIR"
  rsync -a --delete "$WIKI_DIR/" "$DEST_DIR/"
  echo "  ✅ 已同步: $WIKI_DIR -> $DEST_DIR"
fi

echo ""
echo "✅ 知识库初始化完成"
